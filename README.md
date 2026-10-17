# Domoticz Plugin for Huawei SUN2000 Inverter

### Updated for Python 3.13 and the `huawei-solar` 2.x API
### Reliable asynchronous Modbus TCP communication, split polling and automatic recovery (plugin v3.2)

## 📌 17.10.2026 Update

**Plugin version 3.2** improves connection recovery and register polling while preserving the original **24 Domoticz devices**, their device IDs, unit numbers and data formats.

**Tested working environment:**

- **Python:** 3.13.9
- **huawei-solar:** 2.5.0
- **pymodbus:** 3.11.4
- **Communication:** Modbus TCP, port 502, slave ID 1

The plugin also contains compatibility handling for `huawei-solar 2.4.0` (tested separately with `pymodbus 3.8.6`). These are specific supported version combinations, **not open-ended minimum version requirements**.

> **Important:** `huawei-solar` **3.x is not supported** by this plugin release. The 3.x library introduced a different client/device API and uses `tmodbus` instead of `pymodbus`. Do **not** run `pip install -U huawei-solar` on an existing v3.2 installation without planning a migration.

### Changes in plugin v3.2

- Retains one dedicated `asyncio` event loop for the lifetime of the plugin instance; reconnects do not recreate the loop.
- Works around a shared `asyncio.Event` issue affecting TCP clients in the supported `huawei-solar` 2.x versions.
- Closes partially opened clients if bridge initialization fails.
- Closes established connections with `await bridge.stop()` instead of calling a nonexistent `client.close()` API.
- Uses bounded connect, polling and close operations, with more informative error messages.
- Polls the **23 normal measurement/status register names** separately from the **3 alarm register names**, avoiding an unwanted Modbus read across a register gap.
- Falls back to individual alarm reads if the alarm group fails; production measurements can continue updating even when alarm data are incomplete.
- Keeps the existing devices and their historical data when upgrading in place.

**Recovery test:** The Ethernet port connected to the inverter was disabled on a MikroTik router and later re-enabled. The plugin detected the communication failure, retried periodically, reconnected automatically and resumed Domoticz updates without restarting Domoticz. This confirms recovery in the tested environment; it is not a guarantee for all inverter/dongle firmware versions.

---

# 🌞 Domoticz Plugin for Huawei SUN2000 Inverter

Special thanks to **JWGracht** for the original concept and inspiration: [JWGracht/Domoticz-Huawei-Inverter](https://github.com/JWGracht/Domoticz-Huawei-Inverter).

This plugin allows Domoticz to communicate with compatible Huawei SUN2000 inverters over **Modbus TCP/IP**, retrieving operational data including:

- PV voltage and current
- Grid voltage and current
- Active, reactive and input power
- Internal and module temperatures
- Inverter efficiency
- Device status, fault codes and alarms
- Daily and accumulated energy yield

The plugin **automatically creates 24 Domoticz devices** when they are missing. It updates their readings at a configurable interval (**minimum 60 seconds**), as long as the inverter responds and the required registers are readable.

---

# ⚙️ Requirements

- **Domoticz** with Python plugin support enabled
- **Python 3.13** (tested with 3.13.9)
- Supported Python library combinations:

  | `huawei-solar` | `pymodbus` | Status |
  |---|---|---|
  | **2.5.0** | **3.11.4** (3.11.x family) | Tested on the running system; recommended |
  | 2.4.0 | 3.8.6 (compatible 3.8.x family) | Tested in standalone diagnostics; compatibility path included |
  | **3.x** | Uses `tmodbus` | **Not supported by plugin v3.2** |

- Modbus TCP enabled on the inverter or communication device (for example, an SDongle)
- An IP address reachable from the Domoticz host; a static or DHCP-reserved address is recommended
- A reachable TCP port (commonly **502**, depending on the installation)
- A compatible device/register implementation; availability can vary by inverter, dongle and firmware

**Recommended dependency installation** (in the **same Python environment used by Domoticz**):

```bash
python3 -m pip install "huawei-solar==2.5.0" "pymodbus==3.11.4"
```

Check the versions before installing or changing packages:

```bash
python3 --version
python3 -m pip show huawei-solar pymodbus
```

If Domoticz runs under another Python interpreter or virtual environment, use that interpreter's `-m pip`. On distributions with an externally managed Python environment, follow your deployment's package/virtual-environment procedure rather than forcing a system-wide install. Also consider other plugins that may depend on different versions of these packages.

---

# 🧠 Architecture Overview (What’s new?)

Plugin v3.2 uses the **`huawei-solar` 2.x bridge API** and a dedicated Python `asyncio` event loop inside the Domoticz plugin. It addresses the connection and error-recovery problems observed with older versions of this plugin.

### ✅ Major improvements compared to older Domoticz plugins:

- Dedicated asynchronous event loop, **kept alive through reconnects**
- `huawei-solar` 2.x bridge lifecycle management and compatible TCP-client event isolation
- Automatic reconnection after Modbus failures and network interruptions
- Cleanup of partially initialized clients on failed startup
- Proper asynchronous bridge shutdown
- Split measurement and alarm polling to avoid rejected combined register ranges
- Alarm fallback that does not discard valid production readings
- Detailed exception logging, including exception types and timeout errors
- Preservation of all original 24 devices and their IDs

**Implementation note:** Domoticz callback functions still synchronously wait for the asynchronous operations to finish. The plugin uses timeouts to limit these waits; it does **not** guarantee that callbacks never block, nor that all Modbus or firmware failures can be recovered instantly.

---

# 🧩 Plugin Components

### **HuaweiSolarPlugin class**

Handles the plugin lifecycle:

- Reading and validating configuration
- Checking supported dependency versions
- Initializing missing Domoticz devices
- Establishing a Modbus TCP bridge
- Scheduling measurement and alarm reads
- Handling polling failures and retrying connections
- Closing connections and releasing the event loop at shutdown

Key attributes:

- `inverterserveraddress`: configured inverter/SDongle IP address
- `inverterserverport`: configured Modbus TCP port
- `data_refresh_interval`: configured refresh interval in seconds (minimum 60)
- `async_loop`: dedicated event loop maintained through reconnections
- `bridge`: connected Huawei Solar bridge, or `None` when unavailable
- `ready`: guards heartbeat callbacks until startup configuration is valid
- `MEASUREMENT_REGISTERS`: 23 non-alarm register names
- `ALARM_REGISTERS`: `ALARM_1`, `ALARM_2`, `ALARM_3`

### Important internal methods

| Method | Purpose |
|---|---|
| `onStart()` | Validate settings and versions, create missing devices, configure the heartbeat and attempt the initial connection |
| `initialize_devices()` | Create the 24 Domoticz devices if their `DeviceID` is missing |
| `_run_async_task()` | Run asynchronous operations on the dedicated loop with a timeout and exception logging |
| `_ensure_modbus_event_isolation()` | Work around the shared TCP-client `asyncio.Event` in supported `huawei-solar` 2.x versions |
| `_create_bridge_safely()` | Create the low-level client and bridge; close the client if initialization fails |
| `_connectInverter()` | Attempt to connect; return `None` on failure so a later refresh cycle can retry |
| `_poll_measurements_and_alarms()` | Read measurements and alarms separately and attempt individual alarm reads if needed |
| `onHeartbeat()` | Trigger polling and reconnect attempts at the configured refresh interval |
| `_closeConnection()` | Stop the bridge while retaining the event loop for a future connection |
| `onStop()` | Stop the connection, cancel remaining tasks and close the event loop |

---

# 🔌 Modbus Communication

Plugin v3.2 targets the **`huawei-solar` 2.4.0 / 2.5.0 API**. It uses the library's asynchronous client and bridge implementation:

```python
from huawei_solar import AsyncHuaweiSolar
from huawei_solar.bridge import _create as _create_bridge_from_client
```

The plugin deliberately creates the low-level client first, then constructs the bridge so it can **close the client if bridge initialization fails**. The upstream `_create()` helper is private; this is why plugin v3.2 restricts the accepted library versions.

The public `create_tcp_bridge()` function is used in many `huawei-solar` 2.x examples, but the plugin's guarded connection path is designed to handle failures during bridge initialization more safely. **Do not assume this API exists in `huawei-solar` 3.x.**

Communication behavior:

- One TCP connection is retained while the inverter responds normally.
- Connection creation, polling and closing are bounded by configured timeouts in code (25 s connect, 40 s polling, 5 s close).
- Measurements and alarms are requested separately through `bridge.batch_update()`.
- Communication failure triggers bridge cleanup and a later reconnect attempt; the plugin's event loop remains alive.
- The inverter Modbus **slave ID is fixed at 1** in plugin v3.2; it is not a user-configurable parameter.

**Avoid simultaneous Modbus clients** when troubleshooting. Some inverter/dongle configurations restrict concurrent Modbus sessions or behave inconsistently when multiple clients connect.

---

# 📊 Plugin Communication and Data

The plugin reads 26 Huawei register **names** in total, divided into two logical groups:

**23 measurement/status registers:**

- PV string 1 and 2 voltage and current
- Grid phases L1/L2/L3 voltage and current
- Active, reactive and input power
- Internal, anti-reverse module and inverter module L1/L2/L3 temperatures
- Efficiency, device status and fault code
- Accumulated and daily energy yield

**3 alarm registers:** `ALARM_1`, `ALARM_2`, `ALARM_3`.

The split prevents one `batch_update()` call from merging alarms at **32008–32010** with PV measurements at **32016–32019** into a read across the intervening address range. Some inverter responses reject such combined reads with Modbus exception code **2** (`Illegal Data Address`).

The plugin updates the corresponding Domoticz devices after a successful measurement read:

- **Power:** displayed in W using the values returned by the library.
- **Energy:** the library's kWh values are multiplied by 1,000 before being written to the existing Domoticz energy devices, preserving their original Wh-based `sValue` formats.
- **Status and alerts:** the `Alert` device contains the fault code and alarm values when all alarms are available.
- **Unavailable alarms:** if an alarm group cannot be read, the plugin attempts individual alarm reads. When data remain incomplete, `Alert` reports **`Alarm status unavailable/incomplete`** rather than incorrectly stating the inverter is alarm-free.

If the normal measurement group fails, the plugin does not replace previous measurements with fabricated zeros. The affected Domoticz devices retain their last successfully received readings until communication is restored.

---

# 🕒 Plugin Timing Mechanism

The plugin uses Domoticz's heartbeat callback:

- `Domoticz.Heartbeat(30)` requests a callback approximately every **30 seconds**.
- `onHeartbeat()` increments an internal counter.
- Polling (or a reconnect attempt if disconnected) occurs when `heartbeat_counter * 30 >= data_refresh_interval`.
- The counter is then reset.
- The user-defined refresh interval cannot be less than **60 seconds**; invalid or smaller values fall back to 60 seconds.

Because the heartbeat operates in 30-second increments, the effective polling cadence is rounded up to the next 30-second boundary. For example, a value of 70 seconds results in approximately 90-second intervals, apart from callback scheduling and execution time.

The plugin also attempts an **initial connection during `onStart()`**. If that attempt fails, periodic reconnection occurs on subsequent scheduled refresh cycles. After a successful reconnection, it immediately fetches data rather than waiting for another cycle.

---

# 🛡 Plugin Connection Error Handling

If Modbus communication fails, the plugin:

1. Logs the failure with its exception type and details.
2. Stops the active bridge via `await bridge.stop()` where applicable.
3. Keeps the dedicated `asyncio` event loop alive.
4. Retries the inverter connection at the next **configured refresh cycle**.
5. Resumes reading measurements and alarms automatically when the connection succeeds.

If bridge initialization fails part-way through, the plugin closes the partially created client before retrying. This avoids leaving a partially initialized TCP session behind.

**Alarm-only errors are handled separately:** production measurements can still update, with an incomplete-alarm warning in `Alert`. Alarm read failures are logged on the first incomplete cycle and then periodically to limit repeated log noise.

**Limits:** A communications outage may cause a timeout delay during a Domoticz callback. The plugin does not automatically set power readings to zero when the inverter is unreachable; the last values remain visible and may become stale. Plugin v3.2 does **not** create a separate `Communication Status` device.

**Tested recovery sequence (17 October 2026):** After the inverter's Ethernet switch port was disabled, data polling failed, reconnection attempts repeated at roughly one-minute intervals, and readings resumed automatically shortly after the port was re-enabled. No Domoticz restart was needed.

---

## Domoticz Device Creation and Updates

The `initialize_devices()` function creates **24 devices** when they are not already present. It runs during a valid startup **before an inverter connection is required**, so missing devices can be created even if the inverter is temporarily offline. If required Python dependencies are missing/unsupported or configuration validation fails, initialization is not completed.

**All device names, units, `DeviceID`s, types, subtypes, switch types and update formats are preserved from plugin v2.7.** Existing devices are reused rather than duplicated, and upgrading the plugin in place does not intentionally reset their history.

| Device Name / DeviceID | Unit | Data Type (`dtype`) | Subtype (`stype`) | Switch Type (`switchtype`) | Description |
|---|---:|---|---|---|---|
| PV1 Voltage | 7 | 243 (Voltage) | 8 (Voltage) | None | PV string 1 voltage |
| PV2 Voltage | 22 | 243 (Voltage) | 8 (Voltage) | None | PV string 2 voltage |
| L1 Voltage | 27 | 243 (Voltage) | 8 (Voltage) | None | Grid phase 1 voltage |
| L2 Voltage | 28 | 243 (Voltage) | 8 (Voltage) | None | Grid phase 2 voltage |
| L3 Voltage | 29 | 243 (Voltage) | 8 (Voltage) | None | Grid phase 3 voltage |
| PV1 Current | 30 | 243 (Current) | 23 (Amps) | None | PV string 1 current |
| PV2 Current | 31 | 243 (Current) | 23 (Amps) | None | PV string 2 current |
| L1 Current | 32 | 243 (Current) | 23 (Amps) | None | Grid phase 1 current |
| L2 Current | 33 | 243 (Current) | 23 (Amps) | None | Grid phase 2 current |
| L3 Current | 34 | 243 (Current) | 23 (Amps) | None | Grid phase 3 current |
| Input Power | 35 | 248 (Electric) | 1 (Watts) | None | Inverter input power |
| Active Power | 36 | 248 (Electric) | 1 (Watts) | None | Inverter active power |
| Reactive Power | 37 | 248 (Electric) | 1 (Watts) | None | Inverter reactive power |
| Internal Temp | 38 | 80 (Temperature) | 5 (Celsius) | None | Inverter internal temperature |
| Anti Reverse Temp | 39 | 80 (Temperature) | 5 (Celsius) | None | Inverter anti-reverse module temperature |
| Inverter L1 Modul Temp | 40 | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L1) |
| Inverter L2 Modul Temp | 41 | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L2) |
| Inverter L3 Modul Temp | 42 | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L3) |
| Alert | 14 | 243 (Text) | 19 (Alert) | None | Fault code and alarms; explicitly reports incomplete alarm data |
| Device Status | 43 | 243 (Text) | 19 (Status) | None | Inverter device status |
| Energy Meter | 23 | 243 (Counter) | 29 (kWh) | 4 (kWh) | Current active power (W) and accumulated energy (Wh) |
| Daily Energy Meter | 1 | 243 (Counter) | 29 (kWh) | 4 (kWh) | Daily energy yield (Wh) |
| Total Energy | 26 | 113 (Counter) | 0 (kWh) | None | Total accumulated energy (Wh) |
| Inverter Efficiency | 6 | 243 (Percentage) | 6 (Percentage) | None | Inverter efficiency |

The `_getDevice()` helper locates devices by `DeviceID`. The plugin updates them through `Devices[...].Update(nValue=0, sValue=...)` after polling.

Original `sValue` formats are retained:

```text
Energy Meter:       <active_power_W>;<accumulated_yield_Wh>
Daily Energy Meter: 0;<daily_yield_Wh>
Total Energy:       <accumulated_yield_Wh>
```

When all alarms are available, `Alert` shows the fault code and three alarm lists; when the fault code is zero and all lists are empty, it displays `Error code and alarm free status`.

## Explanation of Data Types and Subtypes

- **Data Type (`dtype`):** Domoticz device category. In this plugin, the existing values include `80` (temperature), `113` (counter), `243` (general-purpose device family) and `248` (electric measurement).
- **Subtype (`stype`):** Identifies the device's measurement representation; examples here include voltage (`8`), current (`23`), temperature (`5`), percentage (`6`), text (`19`) and energy meter (`29`).
- **Switch Type (`switchtype`):** An additional Domoticz device configuration field. Most devices omit it (`None` in the configuration list); the two kWh-style meters use `4`.

These numeric type and subtype codes have intentionally **not changed** in v3.2, to maintain compatibility with existing devices and stored data.

---

# Huawei Inverter Parameter Discovery Script

The following script lists the **register-name constants supplied by the installed `huawei-solar` 2.x library** and performs one optional example read. It does **not** automatically discover every physical register supported by your particular inverter, and the printed constants are symbolic names rather than a complete numeric Modbus address map.

```python
import asyncio
from huawei_solar import AsyncHuaweiSolar, register_names as rn

INVERTER_IP = "x.x.x.x"  # Replace with the inverter IP
MODBUS_PORT = 502
SLAVE_ID = 1

async def main():
    print("Known Huawei Solar register names:")
    for name in sorted(vars(rn)):
        value = getattr(rn, name)
        if name.isupper() and isinstance(value, str):
            print(f"{name}: {value}")

    # Optional communication test. Stop the Domoticz plugin and any other
    # Modbus clients first, as connections may be limited.
    client = await AsyncHuaweiSolar.create(INVERTER_IP, MODBUS_PORT, SLAVE_ID)
    try:
        reading = await client.get(rn.ACTIVE_POWER, SLAVE_ID)
        print(f"\nActive power: {reading.value} {getattr(reading, 'unit', '')}")
    finally:
        await client.stop()

asyncio.run(main())
```

Replace `x.x.x.x` with the appropriate IP address. Use the same supported `huawei-solar` **2.x environment** as plugin v3.2. The example prints the constants exposed by the library and reads only `ACTIVE_POWER`; a name in this list does not mean that every inverter model supports that register.

For diagnosing communication errors, first test a small number of known registers outside Domoticz. Full register-range probing may produce `Illegal Data Address` errors on unsupported ranges.

---

# Installation

### New installation

1. Ensure that **Modbus TCP is enabled** and your Domoticz host can reach the inverter/SDongle.
2. Install a compatible library pair in the **Python environment used by Domoticz** (see Requirements section above). Avoid an unpinned `huawei-solar` upgrade.
3. Clone the plugin repository into your Domoticz plugins directory:

   ```bash
   cd ~/domoticz/plugins
   git clone https://github.com/csutihu/Domoticz-plugin-for-Huawei-SUN2000-Inverter.git
   sudo systemctl restart domoticz
   ```

4. In **Domoticz → Setup → Hardware**, add the **Huawei Solar inverter (modbus TCP/IP)** plugin and configure:

   | Field | Value |
   |---|---|
   | Huawei inverter IP Address | Inverter or SDongle IP address |
   | Port | `502` by default; adjust if your setup uses another port |
   | Data Refresh Interval (sec) | `60` by default; minimum `60` |

5. Enable the hardware and check the Domoticz log. **24 devices** should be created automatically when missing. The plugin can create these devices even before a successful inverter connection, provided startup validation passed.

The Modbus slave ID is **1** in this version and cannot be changed through the hardware settings.

### Upgrade an existing installation

- Back up your current `plugin.py` and, as appropriate, your Domoticz database.
- Update the **existing plugin directory**, rather than installing a second instance of the plugin. For a Git-managed checkout:

  ```bash
  cd /path/to/your/existing/Domoticz-plugin-for-Huawei-SUN2000-Inverter
  cp -a plugin.py plugin.py.backup
  git pull --ff-only
  sudo systemctl restart domoticz
  ```

  If you installed the plugin manually or under a differently named folder, replace the existing `plugin.py` with the v3.2 file instead of cloning an extra copy.

- Keep the existing Domoticz hardware entry and devices. **Do not delete or recreate the hardware** during an ordinary code upgrade, as this may affect device history and automations.
- Check the log for the supported library versions, connection messages and `Data fetch successful. Alarm status: complete`.

---

# 🧪 Troubleshooting (NEW Section)

### ✔ Plugin loads but no data updates

- Check that the plugin logs a real **Modbus target IP and port**, not the default `127.0.0.1`.
- Ensure Modbus TCP is enabled and that the chosen TCP port (often `502`; some configurations use `6607`) is reachable.
- Confirm that the plugin and **Domoticz's Python interpreter** are using supported `huawei-solar` and `pymodbus` versions.
- Verify the address, firewall/router rules and availability of the inverter or SDongle.
- Stop other Modbus clients temporarily to rule out session contention.
- For unreliable wireless connections, check dongle signal quality and stability before experimenting with advanced network settings such as MTU.

### ✔ Connection loops / reconnect every cycle

- Check the TCP IP/port and whether the inverter actually responds to Modbus reads (a successful TCP connection alone is not enough).
- The plugin uses **slave ID 1**, which worked in the tested installation. Other arrangements may require a different unit ID; **v3.2 does not expose a slave-ID setting**.
- Check for concurrent Modbus clients and partially open connections.
- Look for detailed `TimeoutError`, `ModbusIOException` or `ReadException` log entries. The plugin should retry at the next configured refresh interval.

### ✔ `Event ... is bound to a different event loop`

- This error is associated with reuse of asynchronous objects across event loops. Plugin v3.2 retains its event loop through reconnections and applies a per-client event-isolation workaround for supported `huawei-solar` 2.x versions.
- If it appears again, verify that you deployed v3.2 and restart the Domoticz service to clear old Python objects. Include the log and installed library versions in a bug report.

### ✔ `Illegal Data Address` / `ExceptionResponse(... exception_code=2)`

- A requested Modbus address or *combined range* was rejected. One observed problem was a 12-register read starting at **32008**, crossing from alarms into a different PV measurement range.
- Plugin v3.2 separates the **23 measurement/status** register names from **3 alarm** names and falls back to individual alarm reads.
- If this error persists, identify the **register address and length** in the log; another register group or an inverter/firmware-specific unsupported address may be involved.

### ✔ Alarm values are unavailable but production data still update

- This is an intentional partial-success behavior. An alarm group can fail without preventing valid measurements from updating.
- The `Alert` device displays `Alarm status unavailable/incomplete` when one or more alarm values could not be read. It must not be interpreted as an alarm-free condition.

### ✔ `No response received`, `Request cancelled outside pymodbus` or `TimeoutError`

- Investigate cable/switch/dongle state, inverter availability and competing connections.
- After a connection failure, the plugin closes the bridge and tries again on a later refresh cycle. Last successful device readings remain visible until new measurements arrive.
- A physical Ethernet disconnect/reconnect was successfully tested with automatic recovery on 17 October 2026.

### ✔ “Requested registers must be monotonically increasing”

- This error concerns how register lists are passed to the library. Plugin v3.2 uses defined measurement and alarm lists with the `batch_update()` API.
- If this message appears, verify the exact plugin and `huawei-solar` versions and capture the complete traceback; do not assume it is fixed merely because the plugin reports v3.2.

### ✔ `huawei-solar` 3.x installed or unsupported dependency version

- Plugin v3.2 uses `huawei-solar` **2.x**, not the newer 3.x client API.
- Check versions with `python3 -m pip show huawei-solar pymodbus` using the interpreter run by Domoticz.
- Restore a compatible pair (recommended: `huawei-solar==2.5.0` and `pymodbus==3.11.4`) in the appropriate environment. Avoid changing unrelated Python installations.

---

# Result

The following screenshots are retained from the original README and illustrate the Domoticz devices and presentation:

![image](https://github.com/user-attachments/assets/07513d71-8145-4a54-a96b-fc9d6b0c7e28)
![image](https://github.com/user-attachments/assets/aac22280-a384-46d5-9a0f-a691aaad8944)

