# 09.12.2025 Update
Code rework due to python3 and modules upgrades
python version 3.13, huawei-solar modul 2.5.0, pymodbus modul 3.11.4

# Domoticz plugin for Huawei SUN2000 Inverter

First of all, a special thanks to JWGracht for the inspiration!
This Domoticz plugin allows you to monitor your Huawei Solar inverter via Modbus TCP/IP. It retrieves data such as PV voltage and current, grid voltage and current, power production, energy consumption, temperature, and status information.

## Plugin Functionality

The plugin connects to your Huawei Solar inverter using Modbus TCP/IP, retrieves data at a user-defined interval (minimum 60 seconds), and creates or updates corresponding devices in Domoticz.  It handles communication errors gracefully and attempts to reconnect if the connection is lost. The plugin requires the huawei_solar Python library, which supports Modbus communication with the Huawei SUN2000 inverter. To install it, run the following in your terminal:
```bash
pip3 install huawei-solar
```

([Huawei Sun2000 inverter support](https://github.com/wlcrs/huawei-solar-lib))

## Plugin Components

*   **`HuaweiSolarPlugin` class:** This is the main plugin class, handling initialization, data retrieval, device creation/updates, and connection management.
    *   `enabled`: A boolean flag indicating if the plugin is enabled.
    *   `inverterserveraddress`: Stores the inverter's IP address.
    *   `inverterserverport`: Stores the inverter's Modbus TCP port.
    *   `bridge`: Stores the `HuaweiSolarBridge` object for Modbus communication.
    *   `heartbeat_counter`: Counts heartbeat cycles to regulate data refresh intervals.
    *   `data_refresh_interval`: Stores the user-defined data refresh interval (minimum 60 seconds).
    *   `async_loop` : A dedicated asynchronous event loop for handling Modbus communication.
    *   `__init__()`: The class constructor.
    *   `onStart()`: Called when the plugin starts. Initializes the plugin, reads configuration parameters, establishes the Modbus connection, and creates Domoticz devices.
    *   `initialize_devices()`: Creates the necessary Domoticz devices based on a predefined configuration.
    *   `_getDevice()`: Helper function to retrieve a Domoticz device by its ID.
    *   `onStop()`: Called when the plugin stops. Closes the Modbus connection and the dedicated asynchronous event loop.
    *   `onHeartbeat()`: Called every 30 seconds. Triggers data retrieval based on the `data_refresh_interval`.
    *   `_connectInverter()`: Establishes the Modbus connection to the inverter.
    *   `_connectInverter()` : Establishes the stable, persistent Modbus TCP bridge connection (using create_tcp_bridge) without retries.
    *   `_run_async_task()` : Helper function to safely run asynchronous coroutines within the dedicated loop.

*   **Modbus Communication:** The plugin uses the `huawei_solar` library to communicate with the inverter via Modbus TCP/IP.

*   **Domoticz Device Management:** The plugin creates and updates Domoticz devices to reflect the inverter's data.

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

