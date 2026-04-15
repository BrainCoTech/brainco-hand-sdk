# Revo3 Python API Reference

Revo3 (V3) 21-DoF Dexterous Hand — Motor Control & Tactile Sensor API

> SDK: `bc-stark-sdk >= 1.3.5` · Protocol: Modbus RTU @ 5 Mbps

---

## Table of Contents

- [Protocol](#protocol)
- [Quick Start](#quick-start)
- [Connection](#connection)
- [Motor Control](#motor-control)
  - [Device Info](#device-info)
  - [Motor Status](#motor-status)
  - [Position Control](#position-control)
  - [Velocity Control](#velocity-control)
  - [Current Control](#current-control)
  - [MIT Impedance Control](#mit-impedance-control)
  - [Fingertip Cartesian Control](#fingertip-cartesian-control)
  - [Motor Settings](#motor-settings)
- [Tactile Sensor](#tactile-sensor)
  - [Module Enable/Disable](#module-enabledisable)
  - [Data Type](#data-type)
  - [Summary Data](#summary-data)
  - [Module Data](#module-data)
  - [All Touch Data](#all-touch-data)
  - [Reset Pressure](#reset-pressure)
- [DataCollector (High-Frequency)](#datacollector-high-frequency)
  - [V3 Basic (Motor Only)](#v3-basic-motor-only)
  - [V3 Full (Motor + Touch)](#v3-full-motor--touch)
  - [Dynamic Frequency Control](#dynamic-frequency-control)
  - [Buffers](#buffers)
- [Hardware Layout](#hardware-layout)
- [Examples](#examples)

---

## Protocol

- **Register map**: `RegAddrRevo3` (addresses 100+, 1000+, 2000+)
- **Joint count**: 21 joints (joint_id: 0~20, excludes 2 wrist motors)
- **Single joint control**: 3 consecutive registers (1000~1002: id + mode + param)
- **Multi-joint control**: 22 consecutive registers (1010~1031: mode + 21 params)
- **MIT control**: 6 consecutive registers (1050~1055), **atomic single write**
- **Motor feedback**: 5 separate groups (2000-2020, 2030-2050, ...), read individually
- **Additional features**: motor protection current, position/speed limits, teaching mode, touch screen switch

### API Overview

| API | Notes |
|-----|-------|
| `v3_set_motor_position` | SingleJointId mode=0 |
| `v3_set_motor_velocity` | SingleJointId mode=1 |
| `v3_set_motor_current` | SingleJointId mode=2 |
| `v3_set_motor_mit` | Atomic MIT: MitJointId 1050~1055 |
| `v3_set_all_motor_positions` | MultiJoint mode=0, 21 joints |
| `v3_set_all_motor_velocities` | MultiJoint mode=1, 21 joints |
| `v3_set_all_motor_currents` | MultiJoint mode=2, 21 joints |
| `v3_get_motor_status_data` | 5×21 register reads |
| `revo3_set_*` | Extended APIs (prefixed `revo3_`) |

Extended APIs (prefixed with `revo3_`):

| API | Description |
|-----|-------------|
| `revo3_single_joint_control(joint_id, mode, param)` | Low-level single joint |
| `revo3_multi_joint_control(mode, params[21])` | Low-level multi-joint |
| `revo3_mit_control(joint_id, kp, kd, pos, vel, torque_ff)` | Atomic MIT control |
| `revo3_multi_mit_set_joint(joint_id, kp, kd, pos, vel, tor)` | Multi-MIT: set one joint (1100+N×5) |
| `revo3_multi_mit_set_all(kp, kd, pos, vel, tor)` | Multi-MIT: all 21 joints interleaved (1100~1204) |
| `revo3_set_all_mit_kp/kd/positions/velocities/torques(values)` | Batch MIT single-parameter (1300~1404) |
| `revo3_set_all_mit_batch(kp, kd, pos, vel, tor)` | Batch MIT all 5 params grouped (1300~1404) |
| `revo3_finger_control(finger_id, mode, params[4])` | Non-thumb finger control (1500~1505) |
| `revo3_thumb_control(mode, params[5])` | Thumb control (1510~1515) |
| `revo3_finger_mit_control(finger_id, params[20])` | Finger MIT (1520~1540) |
| `revo3_thumb_mit_control(params[25])` | Thumb MIT (1550~1574) |
| `revo3_set_global_protect_current(current)` | Global protection current |
| `revo3_set_joint_protect_current(joint_id, current)` | Per-joint protection |
| `revo3_set_joint_position_limits(joint_id, min, max)` | Position limits |
| `revo3_set_joint_speed_limits(joint_id, min, max)` | Speed limits |
| `revo3_set_touch_screen(enabled)` | Touch screen switch |
| `revo3_set_teaching_mode(enabled)` | Teaching mode |
| `revo3_reset_finger_defaults(finger_id)` | Restore finger defaults |
| `revo3_get_all_motor_temperatures()` | Motor temperatures [21] (°C) |
| `revo3_get_motor_temperature(motor_id)` | Single motor temperature |
| `revo3_get_motor_sn(motor_id)` | Motor serial number |
| `revo3_get_all_motor_sns()` | All motor SNs [21] |
| `revo3_get_motor_fw_versions()` | Motor firmware versions [21] |
| `revo3_get_hardware_version()` | Hardware version string |
| `revo3_get_motor_online_status()` | Motor online bitmask |

---

## Quick Start

```python
import asyncio
from bc_stark_sdk import bc_stark_sdk as sdk

sdk.init_logging()

async def main():
    # Auto-detect Revo3 device
    (protocol, port, baudrate, slave_id) = await sdk.auto_detect_modbus_revo3()
    ctx = await sdk.modbus_open(port, baudrate)

    # Read motor status
    status = await ctx.v3_get_motor_status_data(slave_id)
    print(f"Positions: {status.positions}")

    # Position control (motor 0 → 45°)
    await ctx.v3_set_motor_position(slave_id, 0, 45.0)

    # Read touch summary
    summary = await ctx.v3_get_touch_summary(slave_id)
    print(f"Touch summary: {summary}")

    sdk.modbus_close(ctx)

asyncio.run(main())
```

---

## Connection

### Auto-Detect

```python
# Auto-detect Revo3 device (scans all serial ports at 5Mbps)
(protocol_type, port_name, baudrate, slave_id) = await sdk.auto_detect_modbus_revo3()
# Returns: (str, str, int, int)
# e.g., ("modbus", "/dev/ttyUSB0", 5000000, 1)

# With specific port hint
(protocol_type, port_name, baudrate, slave_id) = await sdk.auto_detect_modbus_revo3("/dev/ttyUSB0")
```

### Manual Connection

```python
# Open Modbus connection (Revo3 default: 5Mbps)
ctx = await sdk.modbus_open("/dev/ttyUSB0", 5000000)
slave_id = 1  # default slave ID

# Close connection
sdk.modbus_close(ctx)
```

### Device Identification

```python
device_info = await ctx.get_device_info(slave_id)
# DeviceInfo fields:
#   .hardware_type   → StarkHardwareType enum
#   .sku_type        → SkuType enum
#   .serial_number   → str
#   .firmware_version → str
#   .description     → str

# Check if device supports Revo3 APIs
is_revo3 = device_info.uses_revo3_motor_api()  # → bool
```

---

## Motor Control

### Constants

| Constant        | Value | Description            |
|-----------------|-------|------------------------|
| Motor Count     | 23    | motor_id: 0 ~ 22      |
| Finger Count    | 5     | Thumb, Index, Middle, Ring, Pinky |
| Wrist Motors    | 2     | motor_id: 21, 22       |

### Device Info

```python
fw_version  = await ctx.v3_get_firmware_version(slave_id)   # → str
serial_num  = await ctx.v3_get_serial_number(slave_id)       # → str
hand_type   = await ctx.v3_get_hand_type(slave_id)           # → int/str
temperature = await ctx.v3_get_board_temperature(slave_id)   # → float (°C)
```

### Motor Status

```python
# Read all 23 motors status in a single call
status = await ctx.v3_get_motor_status_data(slave_id)
# V3MotorStatusData fields:
#   .positions   → List[float]  (23 values, degrees)
#   .velocities  → List[float]  (23 values)
#   .currents    → List[float]  (23 values, Amperes)

# Read positions only
positions = await ctx.v3_get_all_motor_positions(slave_id)  # → List[float] (23 values)
```

### Position Control

```python
# Single motor position (degrees, float)
await ctx.v3_set_motor_position(slave_id, motor_id, degrees)
# motor_id: 0~22
# degrees: float
#   Motor 0~18, 21~22: range [-90.0, 90.0]
#   Motor 19~20 (differential): range [-105.0, 105.0]

# Example
await ctx.v3_set_motor_position(slave_id, 0, 45.0)

# Batch: set all 23 motors at once
positions = [30.0] * 23
await ctx.v3_set_all_motor_positions(slave_id, positions)
# positions: List[float] of exactly 23 values
```

### Velocity Control

```python
# Single motor velocity
await ctx.v3_set_motor_velocity(slave_id, motor_id, velocity)
# motor_id: 0~22
# velocity: float, range [0.0, 1000.0]

# Example
await ctx.v3_set_motor_velocity(slave_id, 0, 100.0)
# Stop: set velocity to 0.0
await ctx.v3_set_motor_velocity(slave_id, 0, 0.0)
```

### Current Control

```python
# Single motor current (mA)
await ctx.v3_set_motor_current(slave_id, motor_id, current)
# motor_id: 0~22
# current: float, range [-1024, 1024] mA

# Example
await ctx.v3_set_motor_current(slave_id, 0, 500.0)  # 500 mA
# Stop: set current to 0.0
await ctx.v3_set_motor_current(slave_id, 0, 0.0)
```

### MIT Impedance Control

MIT (Mini Cheetah) impedance control formula:

```
τ = Kp × (P_des - P_act) + Kd × (V_des - V_act) + T_ff
```

| Parameter | Symbol | Range              | Unit    |
|-----------|--------|--------------------|---------|
| Position  | P_des  | [-434.7, 434.7]    | degrees |
| Velocity  | V_des  | [-32767, 32767]    | rpm     |
| Current   | T_ff   | [-1024, 1024]      | mA      |
| Kp        | Kp     | [0, 10.0]          |         |
| Kd        | Kd     | [0, 10.0]          |         |

```python
# Single motor MIT control
await ctx.v3_set_motor_mit(
    slave_id,
    motor_id,          # 0~22
    position,          # float, degrees
    velocity,          # float, rpm
    current,           # float, mA (feedforward torque)
    kp,                # float, position stiffness
    kd                 # float, velocity damping
)

# Example: Motor 0, pos=45°, vel=0, cur=500mA, Kp=5.0, Kd=0.5
await ctx.v3_set_motor_mit(slave_id, 0, 45.0, 0.0, 500.0, 5.0, 0.5)

# Batch: all 23 motors in a single write (115 Modbus registers)
await ctx.v3_set_all_motor_mit(
    slave_id,
    velocities,        # List[float], 23 values
    positions,         # List[float], 23 values
    currents,          # List[float], 23 values
    kp_values,         # List[float], 23 values
    kd_values          # List[float], 23 values
)

# Batch: set Kp/Kd only (46 registers)
await ctx.v3_set_all_motor_mit_params(
    slave_id,
    kp_values,         # List[float], 23 values
    kd_values          # List[float], 23 values
)
```

### Fingertip Cartesian Control

6-DoF per fingertip (5 fingers, no wrist).

```python
# Create FingertipPose
pose = sdk.FingertipPose(x, y, z, rx, ry, rz)
# All axes range: [-100.0, 100.0]

# Set single fingertip pose
await ctx.v3_set_fingertip_pose(slave_id, finger_id, pose)
# finger_id: 0=Thumb, 1=Index, 2=Middle, 3=Ring, 4=Pinky

# Read all fingertip poses
poses = await ctx.v3_get_all_fingertip_poses(slave_id)
# → List[FingertipPose] (5 items)
# Each FingertipPose has: .x, .y, .z, .rx, .ry, .rz
```

### Motor Settings

```python
# Calibration
await ctx.v3_set_calibration_current(slave_id, current)  # float, mA
await ctx.v3_manual_calibration(slave_id)                 # Trigger manual calibration
await ctx.v3_set_auto_calibration(slave_id, enabled)      # bool

# Motion limits
# await ctx.v3_set_max_acceleration(slave_id, accel)     # REMOVED in V1.4
await ctx.v3_set_max_continuous_current(slave_id, current) # float, mA

# Error handling
await ctx.v3_clear_motor_errors(slave_id)

# Protection & configuration
await ctx.revo3_set_global_protect_current(slave_id, current)      # float, mA
await ctx.revo3_set_joint_protect_current(slave_id, joint_id, cur) # joint 0~20, mA
await ctx.revo3_set_joint_position_limits(slave_id, joint_id, min_raw, max_raw)
await ctx.revo3_set_joint_speed_limits(slave_id, joint_id, min_raw, max_raw)
await ctx.revo3_set_touch_screen(slave_id, enabled)                # bool
await ctx.revo3_set_teaching_mode(slave_id, enabled)               # bool
await ctx.revo3_reset_finger_defaults(slave_id, finger_id)         # restore defaults

# Motor diagnostics
temps = await ctx.revo3_get_all_motor_temperatures(slave_id)       # List[int], °C
temp = await ctx.revo3_get_motor_temperature(slave_id, motor_id)   # int, °C
sn = await ctx.revo3_get_motor_sn(slave_id, motor_id)              # str
hw_ver = await ctx.revo3_get_hardware_version(slave_id)            # str
online = await ctx.revo3_get_motor_online_status(slave_id)         # int (bitmask)
```

---

## Tactile Sensor

### Overview

Revo3 has 11 touch modules (388 total sampling points in V1.4):

| Module ID | Name       | Points | Description        |
|-----------|------------|--------|--------------------|
| 0         | Palm       | 36     | Palm pad           |
| 1         | ThumbTip   | 22     | Thumb fingertip    |
| 2         | ThumbPad   | 51     | Thumb pad          |
| 3         | IndexTip   | 21     | Index fingertip    |
| 4         | IndexPad   | 49     | Index pad          |
| 5         | MiddleTip  | 21     | Middle fingertip   |
| 6         | MiddlePad  | 49     | Middle pad         |
| 7         | RingTip    | 21     | Ring fingertip     |
| 8         | RingPad    | 49     | Ring pad           |
| 9         | PinkyTip   | 21     | Pinky fingertip    |
| 10        | PinkyPad   | 49     | Pinky pad          |

Summary register provides 16 aggregated values:

| Index | Pad                 |
|-------|---------------------|
| 0     | Palm                |
| 1     | Thumb Tip           |
| 2     | Thumb Upper Pad     |
| 3     | Thumb Lower Pad     |
| 4     | Index Tip           |
| 5     | Index Upper Pad     |
| 6     | Index Lower Pad     |
| 7     | Middle Tip          |
| 8     | Middle Upper Pad    |
| 9     | Middle Lower Pad    |
| 10    | Ring Tip            |
| 11    | Ring Upper Pad      |
| 12    | Ring Lower Pad      |
| 13    | Pinky Tip           |
| 14    | Pinky Upper Pad     |
| 15    | Pinky Lower Pad     |

### Module Enable/Disable

```python
# Enable all 11 modules (bitmask: bits 0~10)
all_bits = 0x7FF  # 0b111_1111_1111
await ctx.v3_set_all_touch_modules_enabled(slave_id, all_bits)

# Read enabled modules
enabled_bits = await ctx.v3_get_all_touch_modules_enabled(slave_id)
# → int (bitmask), bit i = module i enabled

# Enable/disable single module
await ctx.v3_set_touch_module_enabled(slave_id, module_id, enabled)
# module_id: 0~10
# enabled: bool

# Read single module enabled state
is_enabled = await ctx.v3_get_touch_module_enabled(slave_id, module_id)
# → bool
```

### Data Type

```python
# Set data output type
await ctx.v3_set_touch_data_type(slave_id, data_type)
# data_type: 0 = AD Raw, 1 = Calibrated

# Read current data type
data_type = await ctx.v3_get_touch_data_type(slave_id)
# → int (0 or 1)
```

### Summary Data

```python
# Read summary force values (16 aggregated pad values)
summary = await ctx.v3_get_touch_summary(slave_id)
# → List[int] (16 values, in mN)
# Layout: [palm, thumb_tip, thumb_upad, thumb_lpad, index_tip, ...]
```

### Module Data

```python
# Read single module pressure array
data = await ctx.v3_get_touch_module_data(slave_id, module_id)
# module_id: 0~10
# → List[int] (variable length per module, see table above)

# Example: read palm (29 points)
palm_data = await ctx.v3_get_touch_module_data(slave_id, 0)
print(f"Palm: {len(palm_data)} points, total={sum(palm_data)}")
```

### All Touch Data

```python
# Read all data at once (summary + all 11 module arrays)
touch_data = await ctx.v3_get_all_touch_data(slave_id)
# V3TouchData fields:
#   .summary  → List[int] (16 values)
#   .modules  → List[List[int]] (11 modules, each with variable points)

# V3TouchData is also returned by V3TouchDataBuffer (DataCollector)
```

### Reset Pressure

```python
# Clear single module pressure data
await ctx.v3_reset_touch_pressure(slave_id, module_id)  # module_id: 0~10

# Clear all modules
await ctx.v3_reset_all_touch_pressure(slave_id)
```

---

## DataCollector (High-Frequency)

For real-time monitoring, use `DataCollector` which runs a background thread polling motor/touch data into lock-free ring buffers.

### V3 Basic (Motor Only)

```python
# Create buffer
motor_buffer = sdk.V3MotorStatusBuffer(max_size=1000)

# Create and start collector
collector = sdk.DataCollector.new_v3_basic(
    ctx=ctx,                       # DeviceContext
    motor_buffer=motor_buffer,     # V3MotorStatusBuffer
    slave_id=slave_id,             # int
    motor_frequency=200,           # Hz (macOS: 200, Linux: 2000)
    enable_stats=False             # bool, print stats to console
)
collector.start()

# Read data (non-blocking)
latest = motor_buffer.peek_latest()  # → V3MotorStatusData or None
if latest:
    print(f"Position[0]: {latest.positions[0]}")

all_data = motor_buffer.pop_all()    # → List[V3MotorStatusData], clears buffer

# Stop
collector.stop()
collector.wait()  # Wait for background thread to finish
```

### V3 Full (Motor + Touch)

```python
# Create buffers
motor_buffer = sdk.V3MotorStatusBuffer(max_size=1000)
touch_buffer = sdk.V3TouchDataBuffer(max_size=100)

# Create collector with both motor and touch
collector = sdk.DataCollector.new_v3_full(
    ctx=ctx,
    motor_buffer=motor_buffer,
    touch_buffer=touch_buffer,
    slave_id=slave_id,
    motor_frequency=200,           # Hz (motor polling rate)
    touch_frequency=5,             # Hz (touch is heavy: ~180ms per read)
    enable_stats=False
)
collector.start()

# Read touch data
touch_list = touch_buffer.pop_all()  # → List[V3TouchData]
for td in touch_list:
    print(f"Summary: {td.summary}")   # 16 values
    print(f"Modules: {len(td.modules)}")  # 11 modules
```

### Dynamic Frequency Control

```python
# Update frequencies at runtime (thread-safe, uses atomic variables)
collector.update_motor_frequency(0)     # Disable motor collection
collector.update_touch_frequency(20)    # 20Hz touch

collector.update_motor_frequency(200)   # Re-enable motor at 200Hz
collector.update_touch_frequency(0)     # Disable touch collection
```

### Buffers

| Buffer Class            | Item Type            | Methods                                              |
|-------------------------|----------------------|------------------------------------------------------|
| `V3MotorStatusBuffer`   | `V3MotorStatusData`  | `peek_latest()`, `pop_all()`, `clear()`, `len()`     |
| `V3TouchDataBuffer`     | `V3TouchData`        | `peek_latest()`, `pop_all()`, `clear()`, `len()`     |

**V3MotorStatusData** fields:
- `.positions` → `List[float]` (23 values, degrees)
- `.velocities` → `List[float]` (23 values)
- `.currents` → `List[float]` (23 values, mA)

**V3TouchData** fields:
- `.summary` → `List[int]` (16 values, mN)
- `.modules` → `List[List[int]]` (11 modules)

---

## Hardware Layout

> 📄 Complete joint anatomy, motor photos, and spec diagrams: [revo3_joint_map.md](revo3_joint_map.md)

### Motor → Finger Mapping

```
Finger    Motor IDs (top-to-bottom)        DoF
────────  ──────────────────────────────    ───
Thumb     M18(IP), M17(MCP), M16(CMC-Rot)   3   + M19, M20 (differential)
Index     M15(DIP), M14(PIP), M13(MCP), M12(Abd)   4
Middle    M11(DIP), M10(PIP), M09(MCP), M08(Abd)   4
Ring      M07(DIP), M06(PIP), M05(MCP), M04(Abd)   4
Pinky     M03(DIP), M02(PIP), M01(MCP), M00(Abd)   4
Wrist     M21(Flex/Ext), M22(Abd)            2
                                           ──
                                     Total: 23 motors, 21 DoF
```

### Position Ranges

| Motor ID | Finger | Joint | Range |
|----------|--------|-------|-------|
| M0 | Pinky | Abd | -14° ~ 15° |
| M1~M3 | Pinky | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M4 | Ring | Abd | ±15° |
| M5~M7 | Ring | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M8 | Middle | Abd | ±15° |
| M9~M11 | Middle | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M12 | Index | Abd | ±15° |
| M13~M15 | Index | MCP/PIP/DIP | -5°~90° / -12°~90° / -20°~90° |
| M16 | Thumb | CMC Rotation | -30° ~ 90° |
| M17 | Thumb | MCP | -10° ~ 90° |
| M18 | Thumb | IP | -10° ~ 103° |
| M19 | Thumb | CMC Abd (diff) | 0° ~ 110° |
| M20 | Thumb | CMC Flex (diff) | 0° ~ 75° |
| M21 | Wrist | Flex/Extension | ±60° |
| M22 | Wrist | Abduction | ±25° |

### Touch Module Layout

```
Module  Name        Pts    Location
──────  ──────────  ─────  ──────────────
 0      Palm         36    Palm center
 1      ThumbTip     22    Thumb fingertip
 2      ThumbPad     51    Thumb pad
 3      IndexTip     21    Index fingertip
 4      IndexPad     49    Index pad
 5      MiddleTip    21    Middle fingertip
 6      MiddlePad    49    Middle pad
 7      RingTip      21    Ring fingertip
 8      RingPad      49    Ring pad
 9      PinkyTip     21    Pinky fingertip
10      PinkyPad     49    Pinky pad
                    ─────
            Total:   388   sampling points
```

---

## Examples

| Script                    | Description                            |
|---------------------------|----------------------------------------|
| `revo3/revo3_motor.py`    | Motor control demo (all 5 modes)       |
| `revo3/revo3_timing_test.py` | Single motor timing test w/ DataCollector |
| `revo3/revo3_teaching.py` | Teaching mode: record & playback hand movements |
| `demo/hand_touch_revo3.py`   | Tactile sensor full demo               |

### Run Examples

```bash
# Motor control
python revo3/revo3_motor.py
python revo3/revo3_motor.py --port /dev/ttyUSB0

# Timing test (M3, 5 cycles)
python revo3/revo3_timing_test.py
python revo3/revo3_timing_test.py --motor 5 --cycles 10 --angle 60.0

# Teaching mode (record hand movements, then replay)
python revo3/revo3_teaching.py                                    # Interactive record + playback
python revo3/revo3_teaching.py --save pen_spin.json               # Record and save trajectory
python revo3/revo3_teaching.py --load pen_spin.json --loop 5      # Load and loop playback
python revo3/revo3_teaching.py --speed 0.5                        # Half-speed playback
python revo3/revo3_teaching.py --freq 50                          # Record at 50Hz

# Tactile sensor
python demo/hand_touch_revo3.py
python demo/hand_touch_revo3.py -m /dev/ttyUSB0 5000000 1

# GUI (Revo3 Modbus)
python gui/main.py --revo3-modbus
```

---

## Removed in V1.4

| Feature | Notes |
|---------|-------|
| LED Switch (register 104) | `set_led_enabled()` removed |
| RS485 4Mbps baudrate | Use 2Mbps or 5Mbps |
| Admittance control (mode 3) | Use Impedance (4) or Damping (5) |
| MaxAcceleration (register 115) | `v3_set_max_acceleration()` raises error |

## Motor Status Bitmask (V1.4)

Each motor status/error is a `u16` bitmask:

| Bit | Flag | Condition | Recovery |
|:---:|------|-----------|----------|
| 0 | OverCurrent | Sustained ≥1.5A for 50ms | Auto-stop |
| 1 | OverVoltage | >26V | Reduce supply |
| 2 | UnderVoltage | <8V | Charge battery |
| 3 | OverTemperature | >110°C | Recovers <90°C |
| 4 | CurrentSpike | Peak 2A | Auto-stop |
| 8 | Stalled | Motor blocked | Check obstruction |
| 11 | Running | Motor active | Status, not error |
