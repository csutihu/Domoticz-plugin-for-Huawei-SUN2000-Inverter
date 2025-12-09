# Domoticz Plugin for Huawei SUN2000 Inverter  
### Fully rewritten for Python 3.13 + huawei-solar ≥ 2.5.0  
### Stable asynchronous Modbus TCP bridge (Final Stable Logic)

## 📌 09.12.2025 Update  
This plugin has been fully reworked to support the latest Python and module versions:  
- **Python 3.13**  
- **huawei-solar ≥ 2.5.0**  
- **pymodbus ≥ 3.11.4**

The old plugin was no longer compatible with the updated Huawei Solar library, which changed both its API and Modbus communication layer.  
This release implements an entirely new, modern, asynchronous connection architecture.

---

# 🌞 Domoticz Plugin for Huawei SUN2000 Inverter

Special thanks to **JWGracht** for the original concept and inspiration.

This plugin allows Domoticz to communicate with Huawei SUN2000 inverters over **Modbus TCP/IP**, retrieving live operational data such as:

- PV voltage & current  
- Grid voltage & current  
- Active/reactive/input power  
- Temperatures (internal & module)  
- Inverter efficiency  
- Status, fault codes, alarms  
- Daily & total energy yield  

The plugin creates Domoticz devices automatically and updates their values at a user-defined interval (minimum 60 seconds).

---

# ⚙️ Requirements

- **Domoticz**  
- **Python 3.13**  
- **pip3 install huawei-solar (≥ 2.5.0)**  
- **pymodbus ≥ 3.11.4**  
- Modbus TCP must be enabled on the inverter or SDongle  
- Static or DHCP-reserved inverter IP recommended

---

# 🧠 Architecture Overview (What’s new?)

This plugin is **not** a small update — it is a **complete redesign** based on the new Huawei Solar library API.

### ✅ Major improvements compared to older Domoticz plugins:
- Dedicated asynchronous event loop → stable under Python 3.13  
- Modern **`create_tcp_bridge()`** API for Modbus connection  
- Stable reconnection and error recovery  
- No clashes with Domoticz internal asyncio loops  
- Full compatibility with huawei-solar v2.5+  
- Clean shutdown of Modbus sessions  
- Centralized batch update logic  
- Robust exception handling  

---

# 🧩 Plugin Components

### **HuaweiSolarPlugin class**
Handles the full lifecycle:

- Initialization  
- Connection setup  
- Device creation  
- Timed (heartbeat-based) data acquisition  
- Error handling and reconnection  
- Clean shutdown  

Key attributes:

- `inverterserveraddress`: inverter IP  
- `inverterserverport`: Modbus TCP port  
- `data_refresh_interval`: refresh frequency  
- `async_loop`: **dedicated event loop** for Modbus communication  
- `bridge`: Modbus TCP connection created by `create_tcp_bridge()`  

### Important internal methods

| Method | Purpose |
|-------|---------|
| `onStart()` | Initialize plugin, read settings, create devices, open Modbus connection |
| `initialize_devices()` | Create Domoticz devices if missing |
| `_run_async_task()` | Safely executes async coroutines using the dedicated loop |
| `_connectInverter()` | Creates a stable Modbus TCP connection without retries |
| `onHeartbeat()` | Executes data polling every 30 sec, manages failures & reconnection |
| `onStop()` | Cleanly closes Modbus connection and event loop |

---

# 🔌 Modbus Communication
The plugin uses:
```python
from huawei_solar import create_tcp_bridge
```
This is the recommended method in all modern versions of the library.

It ensures:

*   persistent TCP connection
*   optimized register batching
*   stable asyncio behaviour
*   reduced overhead

## Plugin Communication and Data

The plugin communicates with the Huawei Solar inverter using Modbus TCP/IP. It retrieves various data points, including:

*   PV voltage and current for each PV string.
*   Grid voltage and current for each phase.
*   Active and reactive power.
*   Input power.
*   Inverter internal and module temperatures.
*   Inverter efficiency.
*   Device status.
*   Fault codes and alarms.
*   Accumulated and daily energy yield.

The plugin then updates the corresponding Domoticz devices with this information.

## Plugin Timing Mechanism

The plugin uses Domoticz's heartbeat mechanism to regulate its operations. The `onHeartbeat()` function is called every 30 seconds.  A `heartbeat_counter` is incremented with each heartbeat. When `heartbeat_counter * 30` reaches or exceeds the `data_refresh_interval`, the plugin retrieves data from the inverter and updates the Domoticz devices. The `heartbeat_counter` is then reset to 0. This ensures the data is refreshed at the user-defined interval.

## Plugin Connection Error Handling

The plugin includes error handling for Modbus communication. If a connection error occurs during data retrieval or a timeout happens, the plugin logs the error and attempts to reconnect to the inverter. If the reconnection is successful, the plugin continues to operate normally. If the reconnection fails, the plugin logs the failure and continues to attempt reconnection on subsequent heartbeats.

## Domoticz Device Creation and Updates

The `initialize_devices()` function creates the following Domoticz devices:

| Device Name | Data Type (`dtype`) | Subtype (`stype`) | Switch Type (`switchtype`) | Description |
|---|---|---|---|---|
| PV1 Voltage | 243 (Voltage) | 8 (Voltage) | None | PV string 1 voltage |
| PV2 Voltage | 243 (Voltage) | 8 (Voltage) | None | PV string 2 voltage |
| L1 Voltage | 243 (Voltage) | 8 (Voltage) | None | Grid phase 1 voltage |
| L2 Voltage | 243 (Voltage) | 8 (Voltage) | None | Grid phase 2 voltage |
| L3 Voltage | 243 (Voltage) | 8 (Voltage) | None | Grid phase 3 voltage |
| PV1 Current | 243 (Current) | 23 (Amps) | None | PV string 1 current |
| PV2 Current | 243 (Current) | 23 (Amps) | None | PV string 2 current |
| L1 Current | 243 (Current) | 23 (Amps) | None | Grid phase 1 current |
| L2 Current | 243 (Current) | 23 (Amps) | None | Grid phase 2 current |
| L3 Current | 243 (Current) | 23 (Amps) | None | Grid phase 3 current |
| Input Power | 248 (Electric) | 1 (Watts) | None | Inverter input power |
| Active Power | 248 (Electric) | 1 (Watts) | None | Inverter active power |
| Reactive Power | 248 (Electric) | 1 (Watts) | None | Inverter reactive power |
| Internal Temp | 80 (Temperature) | 5 (Celsius) | None | Inverter internal temperature |
| Anti Reverse Temp | 80 (Temperature) | 5 (Celsius) | None | Inverter anti-reverse module temperature |
| Inverter L1 Modul Temp | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L1) |
| Inverter L2 Modul Temp | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L2) |
| Inverter L3 Modul Temp | 80 (Temperature) | 5 (Celsius) | None | Inverter module temperature (L3) |
| Alert | 243 (Text) | 19 (Alert) | None | Inverter fault codes and alarms |
| Device Status | 243 (Text) | 19 (Status) | None | Inverter device status |
| Energy Meter | 243 (Counter) | 29 (kWh) | 4 (kWh) | Accumulated energy yield |
| Daily Energy Meter | 243 (Counter) | 29 (kWh) | 4 (kWh) | Daily energy yield |
| Total Energy | 113 (Counter) | 0 (kWh) | None | Total energy yield |
| Inverter Efficiency | 243 (Percentage) | 6 (Percentage) | None | Inverter efficiency |

The `_getDevice()` helper function is used to retrieve existing Domoticz device objects by their ID. The `onHeartbeat()` function retrieves data and then updates the Domoticz devices using the `Update()` method, passing the new `nValue` and `sValue` for each device.

## Explanation of Data Types and Subtypes

*   **Data Type (`dtype`):** Specifies the type of data the device represents. Common values include:
    *   `80`: Temperature
    *   `113`: Counter
    *   `243`: Text/Value
    *   `248`: Electric
*   **Subtype (`stype`):** Provides more specific information about the data. For example, for temperature, the subtype might be Celsius or Fahrenheit. For electric measurements, it might be Watts, Amps, or Volts.
*   **Switch Type (`switchtype`):**  Indicates if the device is a switch, and if so, what type (e.g., On/Off, Push Button). If `None`, the device is not a switch.

# Huawei Inverter Parameter Discovery Script

The following Python script can be used to discover all available Modbus registers on your Huawei inverter:

```python
import asyncio
from huawei_solar import AsyncHuaweiSolar, register_names as rn

async def main():
    # Inverter IP and Modbus TCP port
    inverter_ip = "x.x.x.x"  # Replace with your inverter's IP address
    modbus_port = 502

    # Connect to the inverter
    client = await AsyncHuaweiSolar.create(inverter_ip, modbus_port, slave=1)

    # List all registers in a sorted format
    print("\n **Available Registers:**\n")

    for key, value in sorted(rn.__dict__.items()):
        if not key.startswith("__"):  # List only the actual registers
            print(f"{key}: {value}")
asyncio.run(main())
```

Remember to replace "x.x.x.x" with the actual IP address of your Huawei inverter.  This script requires the huawei_solar library to be installed (pip3 install huawei-solar). It will print a list of all available registers and their corresponding Modbus addresses, which can be helpful for further development or customization.

# Installation

```bash
cd ~/domoticz/plugins
git clone https://github.com/csutihu/Domoticz-plugin-for-Huawei-SUN2000-Inverter.git
sudo systemctl restart domoticz
```
# Result
![image](https://github.com/user-attachments/assets/07513d71-8145-4a54-a96b-fc9d6b0c7e28)
![image](https://github.com/user-attachments/assets/aac22280-a384-46d5-9a0f-a691aaad8944)

