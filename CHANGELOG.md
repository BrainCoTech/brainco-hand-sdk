# BrainCo RevoHand SDK Examples Changelog

## v2.0.9 (2026/10/28)

- Updated the Python dependency and C/C++ download defaults to SDK `2.0.9`.
- On Linux, Modbus requests no longer wait for each serial write to drain. Set `STARK_MODBUS_DRAIN_ON_FLUSH=1` before opening the port to restore the previous behavior. CAN FD, macOS, and Windows transports are unchanged.
- The serial change does not establish a guaranteed control and feedback rate for two hands sharing one RS485 bus.

## v2.0.8 (2026/10/19)

- Fixed `stark_get_finger_max_position` (C/C++) and `get_finger_max_position` (Python) reading the setting register instead of the readback register. The getter now reads `952 + finger_id - 1` for the six fingers.
- Updated native library downloads and the Python minimum dependency to `2.0.8`. Public API signatures are unchanged.

## v2.0.7 (2026/10/12)

### RS485 discovery

- Updated the Python dependency to `2.0.7`, which retains all supported FTDI RS485 ports even when channels share a USB serial number. Earlier versions could skip a usable channel during automatic discovery.
- Explicit `port` selection remains available. Close other serial applications before probing; `scan_all=False` still stops after finding the first device.
- Linux x86_64 and ARM64 Python wheels are available for glibc 2.31 (Ubuntu 20.04+) and later. This release does not provide a macOS Python wheel. C/C++ download defaults use `2.0.7` for Linux ARM64/x86_64, macOS ARM64/x86_64 universal, and Windows x64, including the same discovery fix.

## v2.0.6 (2026/10/12)

### Revo2 Touch compatibility

- Use `STARK_HARDWARE_TYPE_REVO2_TOUCH` (`11`) for Revo2 Touch. Hardware value `4` selects Revo1 Advanced Touch; update older integrations that used `4` for Revo2 Touch.
- Added C APIs `stark_enable_touch_sensor_with_status` and `stark_calibrate_touch_sensor_with_status`: `0` indicates transport success; `-1` indicates a null handle or operation failure. Native Modbus RTU waits for the write response; custom callbacks must report transport failures. Success does not confirm physical calibration completion. Keep the handle alive and do not close it concurrently or call these blocking APIs from an SDK transport callback holding the same device lock. The existing asynchronous `void` APIs remain compatible.
- Custom Modbus writes now propagate transport errors and reject incorrect FC06/FC16 response echoes.
- Updated native download defaults and the Python minimum dependency to `2.0.6`. The Linux ARM64 wheel uses `manylinux_2_31` for Ubuntu 20.04 and later; this change does not establish the same compatibility for other wheel platforms.
- C SDK packages include matching headers and the MIT `LICENSE`. Upgrade the library and header together. Windows x64 packages include MinGW and MSVC-format import libraries; Windows runtime and full ROS2/G1 hardware integration remain unverified.

## v2.0.5 (2026/08/31)

### Logging compatibility

- Restored the source- and binary-compatible C `init_logging(log_level)` entry point.
- Added `init_logging_with_options(log_level, enable_file_logging)` for explicit file-output control.
- Existing applications can upgrade without changing their logging call; applications using the temporary `2.0.4` two-argument form must rename it to `init_logging_with_options` when recompiling.
- Updated the native library download scripts and Python dependency to `2.0.5`.

## v2.0.4 (2026/08/31)

### SDK and Logging

- Updated the `bc-stark-sdk` dependency and native library download scripts to `2.0.4`.
- Added explicit file-logging selection to active C/C++ examples. Pass `true` for terminal-plus-file logging or `false` for terminal-only logging.
- Updated communication benchmark helpers to use the SDK's current baudrate conversion and BrainCo CAN lifecycle APIs.
- Recompile C/C++ applications against the `2.0.4` header because the C `init_logging` signature now includes `enable_file_logging`.

---

## v2.0.1 (2026/05/19)

### 🐛 Bug Fixes
- **Auto Detection**: Added full multi-channel and multi-protocol (CAN 2.0 / CANFD) auto-detection support for BrainCo USBCANFD adapters.
- **Motor Calibration**: Resolved an issue preventing successful manual motor calibration on Revo2 devices.

---
## v2.0.0 (2026/05/18)

### Breaking Changes
- **SDK Upgrade**: Upgraded to `bc-stark-sdk` 2.0.0 (Python 3.9 ABI wheels `cp39-abi3`).
- **C/C++ ABI Change**: The `Baudrate` enum has been reordered (e.g., `BAUD5MBPS` changed from 6 to 7). You MUST recompile your C/C++ application against the new `stark-sdk.h` header.
- **Scope Change**: This repository now exclusively targets Revo1 and Revo2 series examples. Support for new-generation devices has been migrated to a dedicated SDK repository.

### Improvements & Fixes
- Removed GUI panels, mock paths, and documentation for unsupported new-generation devices.
- Updated C and Python build scripts and dependency requirements for SDK 2.0.0.
- Cleaned up stale build artifacts and runtime logs.

---

## v1.4.0 (2026/04/15)

### 🚀 Revo2 ArrayPressTouch Device Support
- 3D force + torque (Fx, Fy, Fz, Mx, My) data collection via `ArrayPressureTouchDataBuffer`
- C++ demos: `hand_demo` and `hand_monitor` with `array_pressure` mode
- Python GUI: 2D vector compass visualization for force/torque data

### 🎨 Python GUI
- Touch panels: heatmap visualization and force/pressure support
- Timing test with Revo2 workers and dynamic frequency switching
- i18n support (EN/ZH)

### 🔧 SDK & API Changes
- New hardware types: `Revo2TouchForce3D`, `Revo2TouchArrayPressure`
- New API: `uses_array_pressure_touch_api()`

### 🐛 Bug Fixes
- Fix CAN error frame handling and auto-detect protocol dispatch
- Add `CAN_ERR_FLAG` check in SocketCAN `recv_can`/`recv_canfd`

### 📚 Documentation & Project Structure
- Archive deprecated `linux/` and `windows/` folders to `archive/`
- Add `install_whl.sh` script for Python wheel installation

---

## v1.1.9 (2026/03/03)

### Improvements
- Added 150ms warm-up delay after port open to improve Modbus auto-detection reliability on first attempt

### New Examples
- `c/demo/debug_detect.cpp` — C++ debug tool for Modbus register inspection and raw Protobuf auto-detection

---

## v1.1.6 (2026/02/24)

### New Features
- Auto-detection now supports BrainCo USBCANFD adapter

---

## v1.1.5 (2026/02/09)

### SDK Changes
- Fixed `canfd_ctx.rs` boundary check
- SocketCAN scan now iterates all interfaces instead of single interface
- Added SocketCAN Python bindings (`init_socketcan_canfd`, `close_socketcan`, `socketcan_scan_devices`)

### Example Improvements

#### Runtime CAN Backend Selection
- Changed CAN backend from compile-time to runtime selection
- Use `STARK_CAN_BACKEND` env var or CLI options to select backend
  - `-s` / `-S`: SocketCAN
  - `-z` / `-Z`: ZLG
  - `-c` / `-f`: ZQWL
- Linux builds all backends by default, use `STARK_NO_CAN` to disable CAN support
- ZLG backend now uses dlopen for dynamic loading (no compile-time dependency)

### Other Changes
- Added `zlgcan_linux_utils.py` / `zlgcan_win_utils.py`, `print_finger_touch_data()` utility
- Removed deprecated `zqwl.py`, `zqwl_can.py`, `socketcan_canfd_dfu.py`, `CAN_BACKEND` variable
- Fixed `zlg_canfd_touch_pressure.py` callback signature, added slave_id notes

---

## v1.1.4 (2026/02/09)

### New Features

#### Device Context Query
- Added `stark_get_protocol_type`, `stark_get_port_name`, `stark_get_baudrate`, `stark_get_can_arb_baudrate`, `stark_get_can_data_baudrate` query APIs
- Added `init_device_handler_can()` / `init_device_handler_can_with_hw_type()` CAN device initialization
- Added `StarkProtocolType::Auto = 0` enum value for auto-detecting all protocols

### Example Improvements
- C++: Renamed `CollectorContext` to `DeviceContext`, removed `protocol`, `port_name`, `baudrate` fields, use C API query instead
- C++: CAN initialization functions now use `init_device_handler_can()` to store baudrate
- C++: `stark_auto_detect` return type changed to `StarkProtocolType` enum for type safety
- C++: Fixed `hand_demo.cpp` compile error: use `STARK_PROTOCOL_TYPE_AUTO` instead of literal `0`
- Python: Added comprehensive type annotations

---

## v1.1.2 (2026/02/06)

### New Features

#### Protocol Support Extension
- **ZQWL CAN Built-in** - SDK built-in driver, no extra DLL needed, supports Linux/macOS/Windows
- **SocketCAN Built-in** (Linux) - No external code required
- **Protobuf Protocol** - Revo1 serial protocol, baudrate 115200, Slave ID 10-254

#### Unified Auto Detection
- `auto_detect()` supports Modbus, ZQWL CAN/CANFD multi-protocol auto detection
- `init_from_detected()` initializes device directly from detection result

#### Revo1 Touch API
- Touch sensor support for Modbus and CAN 2.0 protocols
- Support for Revo1Touch and Revo1AdvancedTouch devices

#### New Hardware Types
- `Revo1Advanced` - Gen1 Advanced (serial prefix BCMEL/BCMER)
- `Revo1AdvancedTouch` - Gen1 Advanced Touch (serial prefix BCMTL2/BCMTR2)

#### Examples and Tools
- `c/demo/` - Cross-platform C++ examples (hand_demo, hand_monitor, hand_dfu, auto_detect)
- `python/demo/` - Unified Python examples
- `python/gui/` - GUI debugging tool (for debugging only)

### Migration Guide

#### API Renaming

| Old API | New API |
|---------|---------|
| `is_revo1()` | `uses_revo1_motor_api()` |
| `is_revo1_touch()` | `uses_revo1_touch_api()` |
| `PyDeviceContext` | `DeviceContext` |

> Note: To check if using Revo2 API, use `!uses_revo1_motor_api()` / `!uses_revo1_touch_api()`

#### Initialization API Changes

**Old API:**
```python
sdk.init_config(protocol, log_level)
ctx = PyDeviceContext.init_canfd(master_id)
```

**New API:**
```python
sdk.init_logging(log_level)
ctx = sdk.init_device_handler(StarkProtocolType.CanFd, master_id)
```

#### C Struct Naming Changes

All C exported structs now have `C` prefix: `MotorStatusData` → `CMotorStatusData`, `DeviceInfo` → `CDeviceInfo`, etc.

#### Deprecation Notice
- `linux/` and `windows/` folders are deprecated, please migrate to `c/` folder

---

## v1.0.6 (2026/01/26)

### 🚀 New Features

#### New Hardware Support
- **Revo1Advanced** - Gen1 Advanced (serial prefix BCMEL/BCMER), uses Revo2 API
- **Revo1AdvancedTouch** - Gen1 Advanced Touch (serial prefix BCMTL2/BCMTR2)

#### Serial Number Auto Recognition

| Serial Prefix | Hardware Type |
|---------------|---------------|
| `BCMRL/BCMRR` | Revo1Basic |
| `BCMEL/BCMER` | Revo1Advanced |
| `BCMTL1/BCMTR1` | Revo1Touch |
| `BCMTL2/BCMTR2` | Revo1AdvancedTouch |
| `BCXTL/BCXTR` | Revo2Touch |
| `BCX*` | Revo2Basic |

#### Architecture Optimization
- Motor/touch status uses low-level multi-threaded collection, upper layer passive reading
- Physical mode control logic fix
- Revo2 RS-485 DFU baudrate auto detection
- SocketCAN backend support

#### Auto Detection Enhancement
- Multi-port auto traversal
- Revo1/Revo2/Protobuf protocol auto recognition
- Quick mode for fast detection

### 📚 New Examples
- `revo2_touch_collector.py` - Touch data collection
- `revo2_timing_test_gui.py` - Timing test GUI

### ⚠️ Note
- Revo1Advanced (BCMEL/BCMER) should use examples in `revo2` directory

---

## v1.0.4 (2026/01/23)

- Data Collector support
- Trajectory control support

---

## v1.0.1 (2025/12/23)

- EtherCAT multi-slave communication support

---

## v1.0.0 (2025/12/08)

### 🎉 Official Release
- Support for Revo1 and Revo2 devices
- Support for RS-485, CAN, CANFD, EtherCAT protocols
- Python and C++ example code provided

---

## v0.9.9 (2025/11/19)

- Revo1 Advanced device support
- Unified control parameter range: position 0~1000, speed/current/PWM -1000~+1000

> ⚠️ Revo1 Advanced devices require SDK v0.9.9+

---

## v0.9.8 (2025/11/04)

### 🚀 New Features

#### CAN/CANFD Support
- Revo2 CAN2.0/CANFD protocol stack
- ZLG CAN/CANFD driver wrapper
- CANFD chunked read/write (supports more than 29 registers)

#### EtherCAT Support
- Touch sensor data collection (PDO/SDO)
- Touch pressure sensor support

#### General Features
- ProtectedCurrent read/write API
- `run_action_sequence` action sequence execution
- Serial number device type detection

#### Performance Optimization
- C/C++ `set` commands execute asynchronously
- High-frequency APIs disable retry to avoid command queue buildup

### 🐛 Bug Fixes
- TurboConfig byte order issue
- Modbus C API async call
- DFU upgrade process optimization

---

For questions, visit [Official Documentation](https://www.brainco-hz.com/docs/revolimb-hand/index.html) or contact BrainCo technical support.
