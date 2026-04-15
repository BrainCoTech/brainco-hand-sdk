# Demo Examples

Cross-platform demo programs with auto-detection for devices and protocols.

## Examples

| Example           | Description                          |
| ----------------- | ------------------------------------ |
| `hand_demo`       | Comprehensive demo (8 modes)         |
| `hand_monitor`    | Real-time data monitor               |
| `hand_motor_revo3`   | Revo3 motor control (23 motors)      |
| `hand_touch_revo3`   | Revo3 touch sensor (11 tactile arrays) |
| `hand_monitor_v3` | Revo3 real-time data monitor         |
| `hand_dfu`        | Firmware upgrade                     |
| `auto_detect`     | Device detection                     |

## Build

```bash
make                    # Build all
make hand_demo.exe      # Build single
make clean              # Clean
```

## hand_demo - Comprehensive Demo

```bash
./hand_demo.exe          # Auto-detect, run all demos
./hand_demo.exe 1        # Run specific demo (1-8)
./hand_demo.exe -h       # Show help
```

**Initialization options:**

| Option | Arguments | Description | Platform |
|--------|-----------|-------------|----------|
| (none) | | Auto-detect device and protocol | All |
| `-m` | `<port> <baud> <id>` | Modbus / RS485 | All |
| `-p` | `<port> [id]` | Protobuf (115200 baud, default id=10) | All |
| `-c` | `<port> <baud> <id>` | CAN 2.0 via USB-CAN adapter (BrainCo / ZQWL) | All |
| `-f` | `<port> <arb> <data> <id>` | CANFD via USB-CAN adapter (BrainCo / ZQWL) | All |
| `-b` | `<iface> <id>` | SocketCAN CAN 2.0 (SDK built-in) | Linux |
| `-B` | `<iface> <id>` | SocketCAN CANFD (SDK built-in) | Linux |
| `-s` | `<iface> <id>` | SocketCAN CAN 2.0 (custom callback) | Linux |
| `-S` | `<iface> <id>` | SocketCAN CANFD (custom callback) | Linux |
| `-z` | `<id>` | ZLG USB-CANFD CAN 2.0 | Linux |
| `-Z` | `<id>` | ZLG USB-CANFD CANFD | Linux |
| `-t` | `<type>` | Hardware type override (use before init option) | All |
| `-x` | `<protocol> <id>` | Custom callback mode (hand_demo only) | All |

> **`-b`/`-B` vs `-s`/`-S`**: Both use Linux SocketCAN, but differ in who handles CAN I/O:
> - **`-b`/`-B`** — SDK handles CAN read/write internally. Recommended for most use cases.
> - **`-s`/`-S`** — Example code (`can_common.cpp`) handles CAN read/write via custom callbacks, useful for debugging or custom transport logic.

```bash
./hand_demo.exe                                    # Auto-detect
./hand_demo.exe -m /dev/ttyUSB0 460800 127         # Modbus
./hand_demo.exe -p /dev/ttyUSB0                    # Protobuf (115200 baud, default id=10)
./hand_demo.exe -p /dev/ttyUSB0 10                 # Protobuf with custom slave_id
./hand_demo.exe -c /dev/ttyUSB0 1000000 1          # CAN 2.0 (BrainCo / ZQWL)
./hand_demo.exe -f /dev/ttyUSB0 1000000 5000000 127  # CANFD (BrainCo / ZQWL)
./hand_demo.exe -b can0 1                          # SocketCAN CAN 2.0 - SDK built-in (Linux)
./hand_demo.exe -B can0 127                        # SocketCAN CANFD - SDK built-in (Linux)
./hand_demo.exe -s can0 1                          # SocketCAN CAN 2.0 - custom callback (Linux)
./hand_demo.exe -S can0 127                        # SocketCAN CANFD - custom callback (Linux)
./hand_demo.exe -z 1                               # ZLG CAN 2.0 (Linux)
./hand_demo.exe -Z 127                             # ZLG CANFD (Linux)
./hand_demo.exe -x modbus 127                      # Custom callback
```

**Hardware type override:**

Use `-t <type>` before init option to override auto-detected hardware type:

```bash
./hand_demo.exe -t 6 -z 2                          # ZLG CAN 2.0, slave=2, force Revo2 Touch
./hand_monitor.exe -t 7 -z 2 touch                 # ZLG CAN 2.0, slave=2, force Revo2 Touch Pressure
```

Hardware type values:
| Value | Type |
|-------|------|
| 0 | Revo1 ProtoBuf |
| 1 | Revo1 Basic |
| 2 | Revo1 Touch |
| 3 | Revo1 Advanced |
| 4 | Revo1 Advanced Touch |
| 10 | Revo2 Basic |
| 11 | Revo2 Touch (Capacitive) |
| 12 | Revo2 Touch Pressure (Modulus) |
| 13 | Revo2 Touch Force3D |
| 14 | Revo2 Touch ArrayPressure |
| 20 | Revo3 Ultra (21 DoF) |
| 21 | Revo3 Ultra Touch |
| 22 | Revo3 Ultra Vision Touch |
| 23 | Revo3 Pro (16 DoF) |
| 24 | Revo3 Pro Touch |
| 26 | Revo3 Basic (13 DoF) |
| 27 | Revo3 Basic Touch |

**Demo modes:**

| Mode | Function                                        | Device       |
| ---- | ----------------------------------------------- | ------------ |
| 1    | Position control                                | All          |
| 2    | Speed/current control                           | All          |
| 3    | Advanced control (position+time/speed)          | Revo2        |
| 4    | Action sequences                                | All          |
| 5    | Config info (baudrate/motor params/force level) | All          |
| 6    | Touch sensor                                    | Touch models |
| 7    | Interactive loop                                | All          |
| 8    | Multi-device control                            | All          |

## hand_monitor - Real-time Monitor

```bash
./hand_monitor.exe           # Auto-detect, auto mode
./hand_monitor.exe motor     # Auto-detect, motor data
./hand_monitor.exe touch     # Auto-detect, motor + capacitive touch
./hand_monitor.exe summary   # Auto-detect, motor + pressure summary
./hand_monitor.exe detailed  # Auto-detect, motor + pressure detailed
./hand_monitor.exe dual      # Auto-detect, motor + pressure summary + detailed
./hand_monitor.exe array_pressure  # Auto-detect, ArrayPressure 3D force + torque
```

**Initialization options:**

```bash
./hand_monitor.exe                                    # Auto-detect
./hand_monitor.exe -m /dev/ttyUSB0 460800 127 motor   # Modbus
./hand_monitor.exe -p /dev/ttyUSB0 motor              # Protobuf (115200 baud)
./hand_monitor.exe -c /dev/ttyUSB0 1000000 1 touch    # CAN 2.0 (ZQWL)
./hand_monitor.exe -b can0 1 motor                    # SocketCAN - SDK built-in (Linux)
./hand_monitor.exe -s can0 1 motor                    # SocketCAN - can_common.cpp (Linux)
./hand_monitor.exe -z 1 motor                         # ZLG CAN 2.0 (Linux)
./hand_monitor.exe -Z 127 touch                       # ZLG CANFD (Linux)
./hand_monitor.exe -t 6 -z 2 touch                    # ZLG CAN 2.0 with hw type override
```

| Mode             | Data                             | Device          |
| ---------------- | -------------------------------- | --------------- |
| `motor`          | Position/speed/current           | All             |
| `touch`          | + Capacitive touch               | Touch models    |
| `summary`        | + Pressure summary (6 values)    | Modulus         |
| `detailed`       | + Pressure detailed (per sensor) | Modulus         |
| `array_pressure` | + 3D force + torque (Fx,Fy,Fz,Mx,My) | ArrayPressure |

## hand_dfu - Firmware Upgrade

```bash
./hand_dfu.exe firmware.bin
```

## auto_detect - Device Detection

```bash
./auto_detect.exe
```

---

## Revo3 Examples

Revo3 (V3) uses a different motor architecture (23 motors, 21 DoF) and tactile system (11 sensor arrays).
Dedicated examples are provided:

### hand_motor_revo3 - Motor Control

```bash
./hand_motor_revo3.exe           # Auto-detect
./hand_motor_revo3.exe -m /dev/ttyUSB0 5000000 1    # Manual
```

Demonstrates: position, velocity, current, MIT, and fingertip cartesian control.

### hand_touch_revo3 - Touch Sensor

```bash
./hand_touch_revo3.exe           # Auto-detect
```

Demonstrates: enable/disable touch modules, read summary and per-module pressure data.

### hand_monitor_v3 - Real-time Monitor

```bash
./hand_monitor_v3.exe              # Motor only (V3 Basic DataCollector)
./hand_monitor_v3.exe touch        # Motor + touch (V3 Full DataCollector)
```

Uses `CV3MotorStatusBuffer` + `data_collector_new_v3_basic` (motor mode)
or `CV3MotorStatusBuffer` + `CV3TouchDataBuffer` + `data_collector_new_v3_full` (touch mode)
for high-frequency buffered data collection.

| Mode    | DataCollector          | Buffers                              |
| ------- | ---------------------- | ------------------------------------ |
| (none)  | `new_v3_basic`         | `CV3MotorStatusBuffer`               |
| `touch` | `new_v3_full`          | `CV3MotorStatusBuffer` + `CV3TouchDataBuffer` |

---

## CAN Adapter Guide

### Supported CAN Backends

All backends are compiled by default on Linux. Select at runtime via CLI or environment variable.

| Backend   | Platform      | CLI Options | Environment Variable |
| --------- | ------------- | ----------- | -------------------- |
| SocketCAN | Linux (default) | `-s/-S`   | `STARK_CAN_BACKEND=socketcan` |
| ZLG       | Linux/Windows | `-z/-Z`     | `STARK_CAN_BACKEND=zlg` |
| ZQWL      | All           | `-c/-f`     | - (SDK built-in) |
| SDK SocketCAN | Linux     | `-b/-B`     | - (SDK built-in) |

### ZQWL (SDK Built-in)

SDK built-in support with auto-detection:

```bash
./hand_demo.exe           # Auto-detect all protocols (including ZQWL CAN/CANFD)
./hand_monitor.exe motor  # Auto-detect, motor monitor
```

Manual specification (optional, skip auto-detect):

```bash
./hand_demo.exe -c /dev/ttyUSB0 1000000 1              # CAN 2.0
./hand_demo.exe -f /dev/ttyUSB0 1000000 5000000 127    # CANFD
```

### ZLG (Dynamic Loading)

Requires `libusbcanfd.so` at runtime (download from: https://manual.zlg.cn/web/#/146)

```bash
# Install libusbcanfd.so to /usr/local/lib or current directory

# Run with ZLG backend
STARK_CAN_BACKEND=zlg ./hand_demo.exe -z 1              # ZLG CAN 2.0
STARK_CAN_BACKEND=zlg ./hand_demo.exe -Z 127            # ZLG CANFD
STARK_CAN_BACKEND=zlg ./hand_monitor.exe -z 1 motor     # ZLG CAN 2.0, motor mode
```

**Notes:**

- `-z <slave_id>` - ZLG CAN 2.0 mode
- `-Z <slave_id>` - ZLG CANFD mode
- ZLG library loaded dynamically at runtime (no compile-time dependency)
- macOS not supported

### SocketCAN (Linux)

Two implementations available:

**Option 1: SDK Built-in**

```bash
# Configure interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Run with SDK built-in SocketCAN
./hand_demo.exe -b can0 1       # CAN 2.0
./hand_demo.exe -B can0 127     # CANFD
```

**Option 2: can_common.cpp (default on Linux)**

```bash
# Configure interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Run (SocketCAN is default on Linux)
./hand_demo.exe -s can0 1       # CAN 2.0
./hand_demo.exe -S can0 127     # CANFD
```

> **ZLG USB-CAN/CANFD with SocketCAN**: If using ZLG adapter with SocketCAN driver, see [../platform/linux/README.md](../platform/linux/README.md) for driver installation.

**Environment variables:**

```bash
export STARK_CAN_BACKEND=socketcan    # Explicit SocketCAN (default on Linux)
export STARK_CAN_BACKEND=zlg          # Switch to ZLG
export STARK_SOCKETCAN_IFACE=can0     # Specify interface
```

---

For device types and protocol details, see [parent README](../README.md).
