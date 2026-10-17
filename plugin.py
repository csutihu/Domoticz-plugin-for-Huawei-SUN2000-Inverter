"""
<plugin key="Domoticz-Huawei-Inverter" name="Huawei Solar inverter (modbus TCP/IP)" author="csuti" version="3.2" wikilink="" externallink="https://github.com/csutihu/Domoticz-Huawei-Inverter">
    <description>
        <p>Domoticz plugin for Huawei Solar inverters via Modbus</p>
        <p>Notes:
        <ul style="list-style-type:square">
            <li>Based on a plugin written by JWGracht - Thanks for that! / https://github.com/JWGracht/Domoticz-Huawei-Inverter</li>
            <li>FixIP or static DHCP for inverter</li>
            <li>Modbus connection enabled at the inverter</li>
            <li>Supported: huawei-solar 2.4.0/pymodbus 3.8.x and huawei-solar 2.5.0/pymodbus 3.11.x (huawei-solar 3.x incompatible)</li>
            <li>On startup failure, the partially initialized Modbus client is closed before retry</li>
            <li>The plugin automatically generates the required devices in Domoticz</li>
            <li>All devices are updated every minute</li>
            <li>Measurements and alarms polled separately to avoid crossing unused register gaps</li>
            <li>Alarm errors do not block production measurements; unavailable alarms are reported explicitly</li>
            <li>Communication error handling is included</li>
            <li><b>Minimum Data Refresh Interval is 60 seconds due to Modbus communication error handling!</b></li>
        </ul></p>
    </description>
    <params>
        <param field="Address" label="Huawei inverter IP Address" width="200px" required="true"/>
        <param field="Port" label="Port" width="40px" required="true" default="502"/>
        <param field="Mode1" label="Data Refresh Interval (sec)" width="40px" required="true" default="60"/>
    </params>
</plugin>
"""
import Domoticz
import asyncio
import traceback
from importlib.metadata import version, PackageNotFoundError
from huawei_solar import AsyncHuaweiSolar
from huawei_solar.bridge import _create as _create_bridge_from_client
from huawei_solar import register_names as rn

class HuaweiSolarPlugin:
    enabled = False
    inverterserveraddress = "127.0.0.1"
    inverterserverport = "502"
    bridge = None
    heartbeat_counter = 0 
    data_refresh_interval = 60
    accumulated_yield_energy = 0 

    async_loop = None
    ready = False
    CONNECT_TIMEOUT = 25  # seconds; worst-case cleanup adds up to 5s
    POLL_TIMEOUT = 40  # seconds; 26 register names can result in multiple Modbus requests
    CLOSE_TIMEOUT = 5  # seconds

    # Keep the previous 26 data items, but NEVER batch 32008..32010 alarms
    # with 32016..32019 PV strings: the 32011..32015 gap may be rejected by
    # some inverters as Modbus exception 0x02 (illegal data address).
    MEASUREMENT_REGISTERS = (
        rn.PV_01_VOLTAGE, rn.PV_02_VOLTAGE,
        rn.PHASE_A_VOLTAGE, rn.PHASE_B_VOLTAGE, rn.PHASE_C_VOLTAGE,
        rn.PV_01_CURRENT, rn.PV_02_CURRENT,
        rn.PHASE_A_CURRENT, rn.PHASE_B_CURRENT, rn.PHASE_C_CURRENT,
        rn.ACTIVE_POWER, rn.REACTIVE_POWER, rn.INPUT_POWER,
        rn.INTERNAL_TEMPERATURE, rn.ANTI_REVERSE_MODULE_1_TEMP,
        rn.INV_MODULE_A_TEMP, rn.INV_MODULE_B_TEMP, rn.INV_MODULE_C_TEMP,
        rn.EFFICIENCY, rn.DEVICE_STATUS, rn.FAULT_CODE,
        rn.ACCUMULATED_YIELD_ENERGY, rn.DAILY_YIELD_ENERGY,
    )
    ALARM_REGISTERS = (rn.ALARM_1, rn.ALARM_2, rn.ALARM_3)

    def __init__(self):
        # Same asyncio loop for every connection and reconnect in this instance.
        self.async_loop = asyncio.new_event_loop()
        self.bridge = None
        self.heartbeat_counter = 0
        self.ready = False
        self._alarm_fail_count = 0

    def _run_async_task(self, coro, description="async operation", timeout=40):
        """Execute one Modbus operation with an upper bound on blocking time."""
        if self.async_loop is None or self.async_loop.is_closed():
            raise RuntimeError("Huawei asyncio event loop is unavailable")
        try:
            return self.async_loop.run_until_complete(
                asyncio.wait_for(coro, timeout=timeout)
            )
        except Exception as e:
            # repr(): asyncio.TimeoutError and some connection errors have empty str().
            Domoticz.Error(f"{description} failed: {type(e).__name__}: {e!r}")
            Domoticz.Debug(traceback.format_exc())
            raise

    def _ensure_modbus_event_isolation(self):
        """Fix huawei-solar 2.4/2.5 shared connected_event (class-level Event).

        In huawei_solar.modbus.ModbusConnectionMixin the 2.x library defines
        `connected_event = asyncio.Event()` at CLASS level. Once this Event
        becomes bound to a loop, reconnecting with another loop raises
        `Event ... is bound to a different event loop`.

        Patch TCP client initialization once in this Python interpreter so
        every new client gets its own event. This does not modify installed
        libraries or existing clients; it affects new TCP clients of this class.
        """
        from huawei_solar.modbus import AsyncHuaweiSolarModbusTcpClient
        client_cls = AsyncHuaweiSolarModbusTcpClient
        if getattr(client_cls, "_domoticz_isolated_event_fix", False):
            return
        if not isinstance(getattr(client_cls, "connected_event", None), asyncio.Event):
            Domoticz.Debug("Huawei Modbus class has no shared Event; no patch needed")
            return

        old_init = client_cls.__init__

        def isolated_event_init(self, *args, **kwargs):
            # Shadow the library's class-level Event for EACH new instance.
            self.connected_event = asyncio.Event()
            old_init(self, *args, **kwargs)

        client_cls.__init__ = isolated_event_init
        client_cls._domoticz_isolated_event_fix = True
        Domoticz.Log("Huawei Modbus shared asyncio.Event workaround installed")

    def onStart(self):
        Domoticz.Log("onStart called - Starting V3.2 (split alarm/PV polling)")
        self.ready = False
        if self.async_loop is None or self.async_loop.is_closed():
            self.async_loop = asyncio.new_event_loop()
        self.bridge = None
        self.heartbeat_counter = 0
        self._alarm_fail_count = 0

        # Read configured target before any operation that could exit startup.
        # V3.0 exited on huawei-solar 2.5.0 BEFORE this step and heartbeats
        # attempted to use the default 127.0.0.1:502 instead of the inverter.
        self.inverterserveraddress = Parameters["Address"].strip()
        self.inverterserverport = Parameters["Port"].strip()
        if not self.inverterserveraddress:
            Domoticz.Error("Inverter address is empty; disabling callbacks")
            return
        try:
            port = int(self.inverterserverport)
            if not 1 <= port <= 65535:
                raise ValueError("port is outside the 1-65535 range")
        except ValueError as exc:
            Domoticz.Error(f"Invalid Modbus TCP port: {exc!r}; disabling callbacks")
            return

        try:
            hv = version("huawei-solar")
            pv = version("pymodbus")
        except PackageNotFoundError as exc:
            Domoticz.Error(f"Required Python dependency is missing: {exc!r}")
            return
        Domoticz.Log(f"Python huawei-solar={hv}, pymodbus={pv}")
        if hv not in ("2.4.0", "2.5.0"):
            Domoticz.Error(
                f"Unsupported huawei-solar version {hv}; V3.2 supports 2.4.0 and 2.5.0. "
                "Heartbeats disabled until a compatible version is installed."
            )
            return
        if hv == "2.5.0" and not pv.startswith("3.11."):
            Domoticz.Error(
                f"huawei-solar 2.5.0 expects a compatible pymodbus 3.11.x series; "
                f"found {pv}. Heartbeats disabled."
            )
            return

        # Apply per-client asyncio.Event fix before opening a TCP client.
        try:
            self._ensure_modbus_event_isolation()
        except Exception as exc:
            Domoticz.Error(f"Cannot install Huawei Modbus event isolation: {exc!r}")
            return

        self.initialize_devices()
        try:
            self.data_refresh_interval = int(Parameters["Mode1"].strip())
            if self.data_refresh_interval < 60:
                Domoticz.Error("Data refresh interval cannot be less than 60 seconds. Using default 60 seconds.")
                self.data_refresh_interval = 60
        except (ValueError, TypeError):
            Domoticz.Error("Invalid data refresh interval. Using default 60 seconds.")
            self.data_refresh_interval = 60

        Domoticz.Log(f"Modbus target: {self.inverterserveraddress}:{port}, slave=1")
        Domoticz.Log(f"Data Refresh Interval: {self.data_refresh_interval} seconds.")
        Domoticz.Heartbeat(30)
        self.ready = True
        self.bridge = self._connectInverter()


    def initialize_devices(self):
        devices_config = [
            (7, "PV1 Voltage", 243, 8, None, "PV1 Voltage"),
            (22, "PV2 Voltage", 243, 8, None, "PV2 Voltage"),
            (27, "L1 Voltage", 243, 8, None, "L1 Voltage"),
            (28, "L2 Voltage", 243, 8, None, "L2 Voltage"),
            (29, "L3 Voltage", 243, 8, None, "L3 Voltage"),
            (30, "PV1 Current", 243, 23, None, "PV1 Current"),
            (31, "PV2 Current", 243, 23, None, "PV2 Current"),
            (32, "L1 Current", 243, 23, None, "L1 Current"),
            (33, "L2 Current", 243, 23, None, "L2 Current"),
            (34, "L3 Current", 243, 23, None, "L3 Current"),
            (35, "Input Power", 248, 1, None, "Input Power"),
            (36, "Active Power", 248, 1, None, "Active Power"),
            (37, "Reactive Power", 248, 1, None, "Reactive Power"),
            (38, "Internal Temp", 80, 5, None, "Internal Temp"),
            (39, "Anti Reverse Temp", 80, 5, None, "Anti Reverse Temp"),
            (40, "Inverter L1 Modul Temp", 80, 5, None, "Inverter L1 Modul Temp"),
            (41, "Inverter L2 Modul Temp", 80, 5, None, "Inverter L2 Modul Temp"),
            (42, "Inverter L3 Modul Temp", 80, 5, None, "Inverter L3 Modul Temp"),
            (14, "Alert", 243, 19, None, "Alert"),
            (43, "Device Status", 243, 19, None, "Device Status"),
            (23, "Energy Meter", 243, 29, 4, "Energy Meter"), 
            (1, "Daily Energy Meter", 243, 29, 4, "Daily Energy Meter"),
            (26, "Total Energy", 113, 0, None, "Total Energy"),
            (6, "Inverter Efficiency", 243, 6, None, "Inverter Efficiency")
        ]

        for unit, name, dtype, stype, switchtype, deviceid in devices_config:
            if self._getDevice(deviceid) < 0:
                params = {
                    "Unit": unit,
                    "Name": name,
                    "Type": dtype,
                    "Subtype": stype,
                    "DeviceID": deviceid
                }
                if switchtype is not None:
                    params["Switchtype"] = switchtype

                Domoticz.Device(**params).Create()
                Domoticz.Log(f"Device created: {name} (Unit: {unit})")


    def _getDevice(self, deviceid):
        i = -1
        for Device in Devices:
            if (Devices[Device].DeviceID.strip() == deviceid): 
                i = Device
                break
        return i


    def onStop(self):
        self.ready = False
        Domoticz.Log("onStop called")
        self._closeConnection()
        if self.async_loop is not None and not self.async_loop.is_closed():
            try:
                pending = asyncio.all_tasks(self.async_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.async_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self.async_loop.run_until_complete(self.async_loop.shutdown_asyncgens())
            except Exception as exc:
                Domoticz.Error(f"Error draining asyncio tasks: {exc!r}")
            finally:
                self.async_loop.close()
                Domoticz.Log("Async loop closed on stop")

    async def _poll_measurements_and_alarms(self):
        """Read measurement data independently of alarm registers.

        A huawei-solar 2.x batch_update combines nearby register ranges,
        including gaps. Asking for all 26 values in one batch can create
        FC03(32008,12), spanning the non-universally-readable 32011..32015
        addresses. Split those batches so a rejected alarm block does not
        suppress valid production and energy readings.
        """
        readings = await self.bridge.batch_update(list(self.MEASUREMENT_REGISTERS))
        alarm_readings = {}
        failed = []
        try:
            alarm_readings = await asyncio.wait_for(
                self.bridge.batch_update(list(self.ALARM_REGISTERS)),
                timeout=8,
            )
        except Exception as exc:
            # Rare fallback: one unavailable alarm register should not
            # prevent the others from being read. All operations remain
            # serialized on the SAME event loop and bridge.
            Domoticz.Debug(
                f"Alarm group read failed; trying separate registers: {type(exc).__name__}: {exc!r}"
            )
            for name in self.ALARM_REGISTERS:
                try:
                    one = await asyncio.wait_for(
                        self.bridge.batch_update([name]), timeout=4
                    )
                    alarm_readings.update(one)
                except Exception as one_exc:
                    failed.append(f"{name}: {type(one_exc).__name__}: {one_exc!r}")

        missing = [name for name in self.ALARM_REGISTERS if name not in alarm_readings]
        alarms_complete = not missing
        if not alarms_complete:
            self._alarm_fail_count += 1
            if self._alarm_fail_count == 1 or self._alarm_fail_count % 10 == 0:
                Domoticz.Error(
                    f"Alarm reading incomplete: missing {', '.join(missing)}; "
                    "production data will still update. "
                    + ("; ".join(failed) if failed else "")
                )
        elif self._alarm_fail_count:
            Domoticz.Log("Alarm readings recovered.")
            self._alarm_fail_count = 0

        readings.update(alarm_readings)
        return readings, alarms_complete

    def onHeartbeat(self):
        if not self.ready:
            return
        Domoticz.Debug("onHeartbeat called")

        self.heartbeat_counter += 1
        if self.heartbeat_counter * 30 >= self.data_refresh_interval: 
            self.heartbeat_counter = 0

            if self.bridge is None:
                Domoticz.Error("Inverter connection is not established. Trying to reconnect...")
                self.bridge = self._connectInverter()
                if self.bridge:
                    Domoticz.Log("Reconnected successfully.")
                    # NEM TÉRHETÜNK VISSZA, HA SIKERES A RECONNECT, AZONNAL LE KELL KÉRDEZNI!
                else:
                    return # Visszatér, ha a reconnect sem sikerült

            # The alarm block 32008..32010 is physically separate from PV
            # 32016..32019; never allow batch_update to merge over the gap.
            try:
                Domoticz.Log("Data fetch started (measurement and alarm groups)...")
                result, alarms_complete = self._run_async_task(
                    self._poll_measurements_and_alarms(),
                    "Data polling",
                    timeout=self.POLL_TIMEOUT,
                )
                Domoticz.Log(
                    "Data fetch successful. Alarm status: "
                    + ("complete" if alarms_complete else "unavailable/incomplete")
                )

                # --- ADATOK KINYERÉSE ÉS FRISSÍTÉSE (RÖVIDÍTVE) ---
                pv_01_voltage = result['pv_01_voltage'].value
                pv_02_voltage = result['pv_02_voltage'].value
                pv_01_current = result['pv_01_current'].value
                pv_02_current = result['pv_02_current'].value
                input_power = result['input_power'].value
                phase_A_voltage = result['phase_A_voltage'].value
                phase_B_voltage = result['phase_B_voltage'].value
                phase_C_voltage = result['phase_C_voltage'].value
                phase_A_current = result['phase_A_current'].value
                phase_B_current = result['phase_B_current'].value
                phase_C_current = result['phase_C_current'].value
                active_power = result['active_power'].value
                reactive_power = result['reactive_power'].value
                efficiency = result['efficiency'].value
                internal_temperature = result['internal_temperature'].value
                anti_reverse_module_1_temp = result['anti_reverse_module_1_temp'].value
                inv_module_a_temp = result['inv_module_a_temp'].value
                inv_module_b_temp = result['inv_module_b_temp'].value
                inv_module_c_temp = result['inv_module_c_temp'].value
                device_status = result['device_status'].value
                fault_code = result['fault_code'].value
                if alarms_complete:
                    alarm_1 = result['alarm_1'].value
                    alarm_2 = result['alarm_2'].value
                    alarm_3 = result['alarm_3'].value
                    alert_svalue = (
                        f"Fault code:{fault_code}, Alarm:{alarm_1}, {alarm_2}, {alarm_3}"
                    )
                else:
                    # Do not erroneously claim an alarm-free status when
                    # the inverter refused some/all alarm registers.
                    alert_svalue = (
                        f"Alarm status unavailable/incomplete; Fault code:{fault_code}"
                    )
                accumulated_yield_energy = (result['accumulated_yield_energy'].value*1000)
                daily_yield_energy = (result['daily_yield_energy'].value*1000)

                # --- ESZKÖZ FRISSÍTÉS ---
                Devices[self._getDevice("PV1 Voltage")].Update(nValue=0,sValue=str(pv_01_voltage))
                Devices[self._getDevice("PV2 Voltage")].Update(nValue=0,sValue=str(pv_02_voltage))
                Devices[self._getDevice("PV1 Current")].Update(nValue=0,sValue=str(pv_01_current))
                Devices[self._getDevice("PV2 Current")].Update(nValue=0,sValue=str(pv_02_current))
                Devices[self._getDevice("Input Power")].Update(nValue=0,sValue=str(input_power))
                Devices[self._getDevice("L1 Voltage")].Update(nValue=0,sValue=str(phase_A_voltage))
                Devices[self._getDevice("L2 Voltage")].Update(nValue=0,sValue=str(phase_B_voltage))
                Devices[self._getDevice("L3 Voltage")].Update(nValue=0,sValue=str(phase_C_voltage))
                Devices[self._getDevice("L1 Current")].Update(nValue=0,sValue=str(phase_A_current))
                Devices[self._getDevice("L2 Current")].Update(nValue=0,sValue=str(phase_B_current))
                Devices[self._getDevice("L3 Current")].Update(nValue=0,sValue=str(phase_C_current))
                Devices[self._getDevice("Active Power")].Update(nValue=0,sValue=str(active_power))
                Devices[self._getDevice("Reactive Power")].Update(nValue=0,sValue=str(reactive_power))
                Devices[self._getDevice("Energy Meter")].Update(nValue=0,sValue=str(active_power)+";"+str(accumulated_yield_energy))
                Devices[self._getDevice("Daily Energy Meter")].Update(nValue=0,sValue=f"0;{str(daily_yield_energy)}")
                Devices[self._getDevice("Total Energy")].Update(nValue=0,sValue=str(accumulated_yield_energy))
                Devices[self._getDevice("Inverter Efficiency")].Update(nValue=0,sValue=str(efficiency))
                Devices[self._getDevice("Internal Temp")].Update(nValue=0,sValue=str(internal_temperature))
                Devices[self._getDevice("Anti Reverse Temp")].Update(nValue=0,sValue=str(anti_reverse_module_1_temp))
                Devices[self._getDevice("Inverter L1 Modul Temp")].Update(nValue=0,sValue=str(inv_module_a_temp))
                Devices[self._getDevice("Inverter L2 Modul Temp")].Update(nValue=0,sValue=str(inv_module_b_temp))
                Devices[self._getDevice("Inverter L3 Modul Temp")].Update(nValue=0,sValue=str(inv_module_c_temp))
                Devices[self._getDevice("Device Status")].Update(nValue=0,sValue=str(device_status))

                if alert_svalue == "Fault code:0, Alarm:[], [], []":
                    alert_svalue = "Error code and alarm free status"
                Devices[self._getDevice("Alert")].Update(nValue=0, sValue=alert_svalue)


            except Exception as e:
                Domoticz.Error(f"Data fetch failed: {type(e).__name__}: {e!r}")
                Domoticz.Log("Closing connection and attempting to reconnect on next heartbeat...")
                self._closeConnection() 
                self.heartbeat_counter = 0 
                return
        
    async def _create_bridge_safely(self):
        """Connect using huawei-solar 2.4.0 or 2.5.0, clean up partial initialization.

        The upstream create_tcp_bridge() calls _create(await AsyncHuaweiSolar.create(...))
        without closing the low-level client when _create() raises (for example,
        a read of NB_PV_STRINGS/30071 fails). Using the same upstream _create()
        after creating the client ourselves lets us guarantee cleanup on failure.

        _create is a PRIVATE library helper, hence the narrow version guard.
        """
        client = await AsyncHuaweiSolar.create(
            self.inverterserveraddress,
            int(self.inverterserverport),
            1,
        )
        try:
            return await _create_bridge_from_client(client, 1)
        except BaseException:
            # Cancellation (wait_for timeout) also passes through this branch.
            try:
                await asyncio.wait_for(client.stop(), timeout=self.CLOSE_TIMEOUT)
                Domoticz.Log("Partial Modbus connection closed after failed initialization")
            except Exception as cleanup_exc:
                Domoticz.Error(
                    "Partial Modbus cleanup failed: "
                    f"{type(cleanup_exc).__name__}: {cleanup_exc!r}"
                )
            raise

    def _connectInverter(self):
        Domoticz.Log("Connecting inverter (same loop, cleanup on init error)")
        try:
            bridge = self._run_async_task(
                self._create_bridge_safely(),
                "Inverter connection",
                timeout=self.CONNECT_TIMEOUT,
            )
            Domoticz.Log("Inverter connected successfully")
            return bridge
        except Exception as e:
            Domoticz.Error(
                f"Inverter connection failed: {type(e).__name__}: {e!r}. "
                "Will retry on the next refresh interval."
            )
            return None

    async def _async_stop_bridge(self, bridge):
        """Huawei-solar 2.4.x and 2.5.x: close through bridge.stop().

        bridge.client is an AsyncHuaweiSolar wrapper and has no .close().
        bridge.stop() cancels its heartbeat and calls AsyncHuaweiSolar.stop(),
        which closes the underlying Modbus transport.
        """
        await bridge.stop()
        await asyncio.sleep(0)

    def _closeConnection(self):
        bridge = self.bridge
        self.bridge = None
        if bridge is None:
            return
        Domoticz.Log("Closing inverter bridge via await bridge.stop() (retaining loop)")
        try:
            self._run_async_task(
                self._async_stop_bridge(bridge),
                "Connection close",
                timeout=self.CLOSE_TIMEOUT,
            )
        except Exception as e:
            Domoticz.Error(f"Could not cleanly stop inverter bridge: {type(e).__name__}: {e!r}")
        # Never close/recreate event loop during reconnect. Only onStop closes it.


# --- DOMOTICZ ENTRY POINTS ---

global _plugin
_plugin = HuaweiSolarPlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Generic helper functions for development process
#def DumpConfigToLog():
#    for x in Parameters:
#        if Parameters[x] != "":
#            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
#    Domoticz.Debug("Device count: " + str(len(Devices)))
#    for DeviceName in Devices:
#        Device = Devices[DeviceName]
#        Domoticz.Debug("Device ID:       '" + str(Device.DeviceID) + "'")
#        Domoticz.Debug("--->Unit Count:      '" + str(len(Device.Units)) + "'")
#        for UnitNo in Device.Units:
#            Unit = Device.Units[UnitNo]
#            Domoticz.Debug("--->Unit:           " + str(UnitNo))
#            Domoticz.Debug("--->Unit Name:     '" + Unit.Name + "'")
#            Domoticz.Debug("--->Unit nValue:    " + str(Unit.nValue))
#            Domoticz.Debug("--->Unit sValue:   '" + Unit.sValue + "'")
#            Domoticz.Debug("--->Unit LastLevel: " + str(Unit.LastLevel))
#    return
