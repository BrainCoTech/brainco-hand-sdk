# BrainCo RevoHand Python SDK

[English](README.md) | [中文](README.zh.md)

Complete Python SDK and examples for BrainCo RevoHand devices (Revo1, Revo2, and Revo3 series).

## 📋 Table of Contents

- [System Requirements](#-system-requirements)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Communication Protocols](#-communication-protocols)
- [API Reference](#-api-reference)
- [Examples](#-examples)
- [Utilities](#-utilities)

## 💻 System Requirements

- **Python**: 3.8 ~ 3.12
- **Operating Systems**:
  - macOS 10.15 or later
  - Windows 10 build 10.0.15063 or later
  - Ubuntu 20.04 LTS or later

## 📦 Installation

### Install from PyPI

```bash
pip3 install bc-stark-sdk
```

### Install from OSS (China Mirror)

For users in China or when PyPI is slow, use the install script or download `.whl` directly from Alibaba Cloud OSS:

```bash
# Use install script (auto-detect platform)
bash install_whl.sh 1.4.2 # Replace with actual version if needed
```

Or manually download and install:

```bash
# macOS (Apple Silicon)
pip3 install https://app.brainco.cn/universal/bc-stark-sdk/libs/v[VERSION]/bc_stark_sdk-[VERSION]-cp38-abi3-macosx_11_0_arm64.whl

# macOS (Intel)
pip3 install https://app.brainco.cn/universal/bc-stark-sdk/libs/v[VERSION]/bc_stark_sdk-[VERSION]-cp38-abi3-macosx_10_12_x86_64.whl

# Linux (x86_64)
pip3 install https://app.brainco.cn/universal/bc-stark-sdk/libs/v[VERSION]/bc_stark_sdk-[VERSION]-cp38-abi3-manylinux_2_34_x86_64.whl

# Linux (arm64)
pip3 install https://app.brainco.cn/universal/bc-stark-sdk/libs/v[VERSION]/bc_stark_sdk-[VERSION]-cp38-abi3-manylinux_2_34_aarch64.whl

# Windows (x86_64)
pip3 install https://app.brainco.cn/universal/bc-stark-sdk/libs/v[VERSION]/bc_stark_sdk-[VERSION]-cp38-abi3-win_amd64.whl
```

> **Note:** Replace `[VERSION]` with the desired version (e.g., `1.4.2`). The `abi3-cp38` tag means the wheel is compatible with Python 3.8+.

### Install Other Dependencies

```bash
cd python
pip3 install -r requirements.txt
```

### Dependencies

- `bc-stark-sdk>=1.4.0` - BrainCo Stark SDK core library
- `asyncio>=3.4.3` - Asynchronous I/O support
- `colorlog>=6.9.0` - Colored logging output

## 🚀 Quick Start

### Basic Control Example (Revo1)

```python
import asyncio
from revo1_utils import open_modbus_revo1, libstark

async def main():
    # Auto-detect and connect to device
    client, slave_id = await open_modbus_revo1()

    # Get device information
    device_info = await client.get_device_info(slave_id)
    print(f"Device: {device_info.description}")

    # Control fingers - close grip
    await client.set_finger_positions(slave_id, [600, 600, 1000, 1000, 1000, 1000])
    await asyncio.sleep(1)

    # Open fingers
    await client.set_finger_positions(slave_id, [0] * 6)

    # Clean up
    libstark.modbus_close(client)

asyncio.run(main())
```

### Basic Control Example (Revo2)

```python
import asyncio
from revo2_utils import open_modbus_revo2, libstark

async def main():
    # Auto-detect and connect to device
    client, slave_id = await open_modbus_revo2()

    # Control fingers
    await client.set_finger_positions(slave_id, [400, 400, 1000, 1000, 1000, 1000])
    await asyncio.sleep(1)

    # Clean up
    libstark.modbus_close(client)

asyncio.run(main())
```

## 🔌 Communication Protocols

### Revo1 Supported Protocols

| Protocol        | Description                     | Example Directory        |
| --------------- | ------------------------------- | ------------------------ |
| RS-485 (Modbus) | Serial communication via RS-485 | [revo1/](revo1/)         |
| CAN             | Controller Area Network         | [revo1_can/](revo1_can/) |

### Revo2 Supported Protocols

| Protocol        | Description                     | Example Directory                  |
| --------------- | ------------------------------- | ---------------------------------- |
| RS-485 (Modbus) | Serial communication via RS-485 | [revo2/](revo2/)                   |
| CAN             | Controller Area Network         | [revo2_can/](revo2_can/)           |
| CANFD           | CAN with Flexible Data-Rate     | [revo2_canfd/](revo2_canfd/)       |
| EtherCAT        | Industrial Ethernet protocol    | [revo2_ethercat/](revo2_ethercat/) |

### Revo3 Supported Protocols

| Protocol        | Description                     | Example Directory                  |
| --------------- | ------------------------------- | ---------------------------------- |
| RS-485 (Modbus) | Serial communication via RS-485 | [revo3/](revo3/)                   |

## 📚 API Reference

### Core SDK Module: `bc_stark_sdk`

Import the SDK:

```python
from bc_stark_sdk import main_mod
libstark = main_mod
```

### Connection Management

#### `auto_detect_modbus_revo1(port_name=None, quick=True)`

Auto-detect and connect to Revo1 device via Modbus.

**Parameters:**

- `port_name` (str, optional): Serial port name. `None` for auto-detection.
- `quick` (bool): Quick detection mode. `True` = faster, `False` = comprehensive.

**Returns:** `(protocol, port_name, baudrate, slave_id)`

**Example:**

```python
protocol, port, baud, slave_id = await libstark.auto_detect_modbus_revo1(None, True)
```

#### `auto_detect_modbus_revo2(port_name=None, quick=True)`

Auto-detect and connect to Revo2 device via Modbus.

**Parameters:** Same as `auto_detect_modbus_revo1`

#### `modbus_open(port_name, baudrate)`

Open Modbus connection with specified parameters.

**Parameters:**

- `port_name` (str): Serial port name (e.g., "/dev/ttyUSB0", "COM3")
- `baudrate` (int): Communication baud rate

**Returns:** `DeviceContext` - Client instance

**Example:**

```python
client = await libstark.modbus_open("/dev/ttyUSB0", 115200)
```

#### `modbus_close(client)`

Close Modbus connection and release resources.

**Parameters:**

- `client` (DeviceContext): Client instance to close

#### `auto_detect()` (New in v1.1.0)

Unified auto-detection for all protocols (Modbus, CAN, CANFD).

**Parameters:**

- `scan_all` (bool): If True, scan for all devices. Default: False
- `port` (str, optional): Specific port to scan. Default: None (scan all)
- `protocol` (str, optional): Protocol to use. Default: None (try all)

**Returns:** `list[CDetectedDevice]` - List of detected devices

**Example:**

```python
devices = await libstark.auto_detect()
if devices:
    ctx = await libstark.init_from_detected(devices[0])
```

#### `init_from_detected(device)` (New in v1.1.0)

Initialize device handler from detected device info.

**Parameters:**

- `device` (CDetectedDevice): Device from auto_detect()

**Returns:** `DeviceContext` - Ready-to-use device context

#### `init_device_handler(protocol_type, master_id)` (New in v1.1.0)

Initialize device handler for CAN/CANFD/EtherCAT protocols.

**Parameters:**

- `protocol_type` (StarkProtocolType): Protocol type enum
- `master_id` (int): Master ID (default: 0)

**Returns:** `DeviceContext` - Device context

**Example:**

```python
ctx = libstark.init_device_handler(libstark.StarkProtocolType.CanFd, 0)
```

### Device Information

#### `client.get_device_info(slave_id)`

Get device information and configuration.

**Returns:** `DeviceInfo` object with properties:

- `description` (str): Device description
- `uses_revo1_motor_api()` (bool): Check if device uses Revo1 Motor API
- `uses_revo2_motor_api()` (bool): Check if device uses Revo2 Motor API
- `uses_revo3_motor_api()` (bool): Check if device uses Revo3 Motor API
- `is_touch()` (bool): Check if device has any touch sensors
- `is_capacitive_touch(hw_type)` (bool): Check if device uses Capacitive Touch API (Revo1/Revo2 Touch)
- `is_pressure_touch(hw_type)` (bool): Check if device uses Modulus Pressure Touch API
- `is_force3d_touch(hw_type)` (bool): Check if device uses Force3D Touch API
- `is_array_pressure_touch(hw_type)` (bool): Check if device uses ArrayPressure Touch API

**Example:**

```python
device_info = await client.get_device_info(slave_id)
print(device_info.description)
from common_imports import is_capacitive_touch
if is_capacitive_touch(device_info.hardware_type):
    print("Capacitive Touch-enabled device")
```

#### `client.get_voltage(slave_id)`

Get device battery voltage.

**Returns:** `float` - Voltage in millivolts (mV)

**Example:**

```python
voltage = await client.get_voltage(slave_id)
print(f"Battery: {voltage:.1f} mV")
```

#### `client.get_serialport_baudrate(slave_id)`

Get current serial port baud rate.

**Returns:** `int` - Baud rate value

### Finger Control

#### `client.set_finger_positions(slave_id, positions)`

Set target positions for all fingers.

**Parameters:**

- `slave_id` (int): Device ID
- `positions` (list[int]): Position values for 6 joints [0-1000]
  - Index 0: Thumb
  - Index 1: Thumb Auxiliary
  - Index 2: Index Finger
  - Index 3: Middle Finger
  - Index 4: Ring Finger
  - Index 5: Pinky Finger

**Position Range:** 0 (fully open) to 1000 (fully closed)

**Example:**

```python
# Close grip
await client.set_finger_positions(slave_id, [600, 600, 1000, 1000, 1000, 1000])

# Open all fingers
await client.set_finger_positions(slave_id, [0, 0, 0, 0, 0, 0])

# Custom positions
await client.set_finger_positions(slave_id, [500, 500, 800, 800, 600, 400])
```

#### `client.set_finger_position(slave_id, finger_id, position)`

Set position for a single finger.

**Parameters:**

- `slave_id` (int): Device ID
- `finger_id` (FingerId): Finger identifier enum
  - `libstark.FingerId.Thumb`
  - `libstark.FingerId.ThumbAux`
  - `libstark.FingerId.Index`
  - `libstark.FingerId.Middle`
  - `libstark.FingerId.Ring`
  - `libstark.FingerId.Pinky`
- `position` (int): Target position [0-1000]

**Example:**

```python
# Close pinky finger only
await client.set_finger_position(slave_id, libstark.FingerId.Pinky, 1000)
```

#### `client.set_finger_speeds(slave_id, speeds)`

Set movement speeds for all fingers (speed control mode).

**Parameters:**

- `slave_id` (int): Device ID
- `speeds` (list[int]): Speed values for 6 joints
  - Positive values: Close direction
  - Negative values: Open direction
  - Range: typically -100 to 100

**Example:**

```python
# Close all fingers at speed 100
await client.set_finger_speeds(slave_id, [100] * 6)

# Open all fingers at speed -100
await client.set_finger_speeds(slave_id, [-100] * 6)
```

### Motor Status

#### `client.get_motor_status(slave_id)`

Get current motor status including positions, currents, and states.

**Returns:** `MotorStatusData` object with properties:

- `positions` (list[int]): Current positions [0-1000] for 6 joints
- `currents` (list[int]): Current values for 6 motors
- `states` (list[int]): Motor state flags for 6 motors
- `description` (str): Human-readable status description
- `is_idle()` (bool): Check if motors are idle
- `is_closed()` (bool): Check if fingers are closed
- `is_opened()` (bool): Check if fingers are opened

**Example:**

```python
status = await client.get_motor_status(slave_id)
print(f"Positions: {list(status.positions)}")
print(f"Currents: {list(status.currents)}")
print(f"Is idle: {status.is_idle()}")
print(f"Is closed: {status.is_closed()}")
```

### Force Control (Revo1 Basic)

#### `client.get_force_level(slave_id)`

Get current force level setting.

**Returns:** `int` - Force level (device-specific range)

#### `client.set_force_level(slave_id, level)`

Set force level for grip strength.

**Parameters:**

- `slave_id` (int): Device ID
- `level` (int): Force level value

**Note:** Only available on non-touch devices. Touch devices use current control.

### Utility Functions

#### Port Detection

```python
from revo1_utils import get_stark_port_name

# Get first available port
port_name = get_stark_port_name()
```

#### Angle/Position Conversion (Revo1)

```python
from revo1_utils import convert_to_position, convert_to_angle

# Convert angles to positions
angles = [30, 45, 35, 35, 35, 35]  # degrees
positions = convert_to_position(angles)  # [0-1000]

# Convert positions to angles
positions = [500, 500, 500, 500, 500, 500]
angles = convert_to_angle(positions)  # degrees
```

#### Current Conversion (Revo1)

```python
from revo1_utils import convert_to_mA

# Convert raw current values to milliamps
raw_currents = [100, 120, 110, 115, 105, 108]
currents_mA = convert_to_mA(raw_currents)
```

#### Shutdown Event Handler

```python
from common_utils import setup_shutdown_event

async def main():
    shutdown_event = setup_shutdown_event(logger)

    # Your code here...

    # Wait for Ctrl+C or shutdown signal
    await shutdown_event.wait()
```

### Logging

```python
from logger import getLogger
import logging

# Get logger with INFO level
logger = getLogger(logging.INFO)

# Get logger with DEBUG level
logger = getLogger(logging.DEBUG)

# Use logger
logger.info("Information message")
logger.debug("Debug message")
logger.warning("Warning message")
logger.error("Error message")
```

Logs are automatically saved to `logs/` directory with timestamps.

## 📂 Examples

### Recommended: Unified Demo Examples

The `demo/` directory contains unified examples that work with all protocols and device types:

| Example | Description | Usage |
|---------|-------------|-------|
| [auto_detect.py](demo/auto_detect.py) | Auto-detect all devices | `python demo/auto_detect.py` |
| [hand_demo.py](demo/hand_demo.py) | Basic control demo | `python demo/hand_demo.py` |
| [hand_monitor.py](demo/hand_monitor.py) | Real-time data monitor | `python demo/hand_monitor.py` |
| [hand_dfu.py](demo/hand_dfu.py) | Firmware upgrade | `python demo/hand_dfu.py` |

**Supported protocols via command line options:**
```bash
# Auto-detect (recommended)
python demo/hand_monitor.py

# Modbus RS-485
python demo/hand_monitor.py -m /dev/ttyUSB0 460800 127

# ZQWL CAN/CANFD
python demo/hand_monitor.py -c /dev/ttyUSB0 1000000 1      # CAN 2.0
python demo/hand_monitor.py -f /dev/ttyUSB0 1000000 5000000 127  # CANFD

# SocketCAN (Linux, SDK built-in)
python demo/hand_monitor.py -b can0 1    # CAN 2.0
python demo/hand_monitor.py -B can1 0x7e # CANFD

# ZLG USB-CAN (Linux)
python demo/hand_monitor.py -z 2         # CAN 2.0
python demo/hand_monitor.py -Z 0x7e      # CANFD
```

**Detailed Guide:** [Demo README](demo/README.md)

### 🖥️ Unified Native GUI

The SDK provides a complete native application under `gui/main.py` which unifies connection management, multi-modal tactile charting, motor tuning, and DFUs all in one cross-platform PyQt6 interface:

| Application | Description | Usage |
|---------|-------------|-------|
| [gui/main.py](gui/main.py) | Full-featured unified GUI application | `python gui/main.py` |

---

### Legacy Examples (Protocol-Specific)

> **Note:** The following directories contain protocol-specific examples. They are kept for reference but we recommend using the unified `demo/` examples above.

#### Revo1 Examples

| Example         | Description                         | File                                                               |
| --------------- | ----------------------------------- | ------------------------------------------------------------------ |
| Basic Control   | Get device info, control fingers    | [revo1_get.py](revo1/revo1_get.py)                                 |
| Auto Control    | Automatic grip/open cycle           | [revo1_ctrl.py](revo1/revo1_ctrl.py)                               |
| Dual Hand       | Control two hands simultaneously    | [revo1_ctrl_dual.py](revo1/revo1_ctrl_dual.py)                     |
| Multi Hand      | Control multiple hands              | [revo1_ctrl_multi.py](revo1/revo1_ctrl_multi.py)                   |
| Action Sequence | Execute predefined action sequences | [revo1_action_seq.py](revo1/revo1_action_seq.py)                   |
| Configuration   | Read/write device configuration     | [revo1_cfg.py](revo1/revo1_cfg.py)                                 |
| Firmware Update | OTA firmware update                 | [revo1_dfu.py](revo1/revo1_dfu.py)                                 |
| Touch Sensors   | Touch sensor data reading           | [revo1_touch.py](revo1/revo1_touch.py)                             |
| Comm Test       | Communication frequency test        | [revo1_comm_frequency_test.py](revo1/revo1_comm_frequency_test.py) |
| Motor Collector | Motor data collection               | [revo1_basic_collector.py](revo1/revo1_basic_collector.py)         |
| Touch Collector | Touch data collection               | [revo1_touch_collector.py](revo1/revo1_touch_collector.py)         |

**Detailed Guide:** [Revo1 RS-485 README](revo1/README.md)

### Revo1 CAN Examples

**Detailed Guide:** [Revo1 CAN README](revo1_can/README.md)

### Revo2 Examples

| Example            | Description                         | File                                                                         |
| ------------------ | ----------------------------------- | ---------------------------------------------------------------------------- |
| Basic Control      | Get device info, control fingers    | [revo2_ctrl.py](revo2/revo2_ctrl.py)                                         |
| Left Hand          | Control left hand                   | [revo2_ctrl_left.py](revo2/revo2_ctrl_left.py)                               |
| Right Hand         | Control right hand                  | [revo2_ctrl_right.py](revo2/revo2_ctrl_right.py)                             |
| Dual Hand          | Control two hands simultaneously    | [revo2_ctrl_dual.py](revo2/revo2_ctrl_dual.py)                               |
| Multi Hand         | Control multiple hands              | [revo2_ctrl_multi.py](revo2/revo2_ctrl_multi.py)                             |
| Action Sequence    | Execute predefined action sequences | [revo2_action_seq.py](revo2/revo2_action_seq.py)                             |
| Configuration      | Read/write device configuration     | [revo2_cfg.py](revo2/revo2_cfg.py)                                           |
| Firmware Update    | OTA firmware update                 | [revo2_dfu.py](revo2/revo2_dfu.py)                                           |
| Touch Sensors      | Touch sensor data reading           | [revo2_touch.py](revo2/revo2_touch.py)                                       |
| Touch Pressure     | Pressure sensor data                | [revo2_touch_pressure.py](revo2/revo2_touch_pressure.py)                     |
| Motor Collector    | Motor data collection               | [revo2_basic_collector.py](revo2/revo2_basic_collector.py)                   |
| Touch Collector    | Touch data collection               | [revo2_touch_collector.py](revo2/revo2_touch_collector.py)                   |
| Pressure Collector | Pressure data collection            | [revo2_touch_pressure_collector.py](revo2/revo2_touch_pressure_collector.py) |

**Detailed Guide:** [Revo2 RS-485 README](revo2/README.md)

### Revo2 CAN Examples

**Detailed Guide:** [Revo2 CAN README](revo2_can/README.md)

### Revo2 CANFD Examples

Supports ZLG USBCAN-FD and ZQWL CANFD devices.

**Detailed Guide:** [Revo2 CANFD README](revo2_canfd/README.md)

### Revo2 EtherCAT Examples

| Example         | Description                    |
| --------------- | ------------------------------ |
| SDO Operations  | Service Data Object read/write |
| PDO Operations  | Process Data Object control    |
| Firmware Update | OTA via EtherCAT               |

**Detailed Guide:** [Revo2 EtherCAT README](revo2_ethercat/README.md)

### Revo3 Examples

Supports the advanced 21 DOF dexterous hand (Revo3).

| Example         | Description | File |
| --------------- | ----------- | ---- |
| Motor Demo      | Basic configuration and 21 DOF control | [revo3_motor.py](revo3/revo3_motor.py) |
| Teaching Mode   | Drag and teach trajectory recording    | [revo3_teaching.py](revo3/revo3_teaching.py) |
| Benchmark       | High-frequency latency/jitter profiling| [revo3_benchmark.py](revo3/revo3_benchmark.py) |

**Detailed Guide:** [Revo3 README](revo3/README.md)

## 🛠️ Utilities

### Common Utilities (`common_utils.py`)

- `setup_shutdown_event(logger)` - Graceful shutdown handler for async applications

### Logger (`logger.py`)

- RFC3339 timestamp format
- Colored console output
- Automatic file logging to `logs/` directory
- Configurable log levels

### Device-Specific Utilities

- **Revo1**: `revo1_utils.py` - Connection helpers, angle/position conversion, current conversion
- **Revo2**: `revo2_utils.py` - Connection helpers, position state checking

## 📖 Additional Open Source Resources

- 🤖 **BrainCo Open Source Hub**: [BrainCoTech GitHub Organization](https://github.com/BrainCoTech) - Discover latest firmware updates, URDF models, and ecosystem integrations
- 📖 **Official Documentation**: [BrainCo Dexterous Hand Docs](https://www.brainco-hz.com/docs/revolimb-hand/index.html)
- 💽 **Firmware Releases**: [revo-hand-firmware](https://github.com/BrainCoTech/revo-hand-firmware) - Official firmware variants for Revo devices
- 🦾 **ROS / ROS 2 Integration**:
  - [brainco_hand_ros2](https://github.com/BrainCoTech/brainco_hand_ros2) - Official ROS 2 Driver
  - [ros2_control_demos](https://github.com/BrainCoTech/ros2_control_demos) - ROS 2 Control integration examples
  - URDF Models: [ROS 2](https://github.com/BrainCoTech/revo2_description) | [ROS 1](https://github.com/BrainCoTech/revo2_description_ros1)
- 🎮 **Simulation**:
  - [BrainCo Isaac Lab (RevoLab)](https://github.com/BrainCoTech/RevoLab) - Reinforcement learning environments built upon NVIDIA Isaac Lab
- 🌐 **Ecosystem App Guides**:
  - [Unitree G1 Humanoid Integration](https://github.com/BrainCoTech/unitree-g1-brainco-hand)
  - [6-DoF Robot Arm Integration](https://www.brainco-hz.com/docs/revolimb-hand/ecology/mechanical_revo2.html)
  - [Teleoperation via EMG & Data Gloves](https://www.brainco-hz.com/docs/revolimb-hand/ecology/arm.html)

## 📝 Notes

- All async functions must be called with `await` inside an async context
- Always close connections with `libstark.modbus_close(client)` when done
- Position values range from 0 (open) to 1000 (closed) for all devices
- Touch-enabled devices use current control instead of force levels
- Use quick detection mode for faster connection in production environments

## ❓ Troubleshooting

### Serial Port Permission Denied (Linux)

```bash
# Check current permissions and group
ls -l /dev/ttyUSB0
# Output: crw-rw---- 1 root dialout ...

# Method 1 (Recommended): Add user to dialout group (permanent, requires re-login)
sudo usermod -aG dialout $USER
# Then log out and log back in. Verify with:
groups  # Should include 'dialout'

# Method 2: Temporary permission change (resets after reboot or re-plug)
sudo chmod 666 /dev/ttyUSB0

# Method 3: Run with sudo
sudo python3 your_script.py
```

### Serial Port Permission Denied (macOS)

```bash
# macOS serial ports are typically /dev/cu.usbserial-* or /dev/tty.usbserial-*
# Usually no extra permissions needed. If permission denied:
sudo chmod 666 /dev/cu.usbserial-*
```

### baudrate TypeError

If you see `TypeError: argument 'baudrate': 'int' object cannot be converted to 'Baudrate'`, use the `modbus_open` wrapper from `common_imports` which auto-converts int to `Baudrate` enum:

```python
from common_imports import modbus_open

# Accepts both int and Baudrate enum
client = await modbus_open("/dev/ttyUSB0", 5000000)
```

## 🤝 Support

Need help? Reach out to us through the following channels:

- 📋 **Submit a ticket**: [https://web.static.brainco.cn/work-order](https://web.static.brainco.cn/work-order)
- 🐙 **GitHub**: [https://github.com/BrainCoTech](https://github.com/BrainCoTech)
- 💡 **References**: Check the example code in subdirectories and review the API documentation above
- 💬 **Direct Support**: Contact the BrainCo technical support team

---

**Version:** Requires `bc-stark-sdk >= 1.4.2`
