#!/usr/bin/env python3
"""
Stark Revo3 (V3) Motor Control Demo - 21 DoF Dexterous Hand

Demonstrates V3-specific motor control APIs:
  - Single/batch motor position, velocity, current control
  - MIT impedance control (force-position hybrid)
  - Motor status monitoring
  - Single/multi joint control with V3ControlMode
  - MIT joint control (τ = Kp*(pos_ref − pos) + Kd*(vel_ref − vel) + τ_ff)
  - Motor parameter config (protection current, position/speed limits)
  - Hardware version, motor online status, teaching mode
  - Peripheral switches (LED, buzzer, vibration, touch screen)

Run:
    python hand_motor_revo3.py                      # Auto-detect
    python hand_motor_revo3.py -m <port> 5000000 1  # Manual Modbus
"""

import asyncio
import sys
import os
import argparse

# Setup path and imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import sdk, check_sdk, logger
from common_init import (
    DeviceContext,
    parse_args_and_init,
    cleanup_context,
    auto_detect_and_init,
)

check_sdk()

REVO3_MOTOR_COUNT = 21
REVO3_FINGER_COUNT = 5
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


# =============================================================================
# Demo Functions
# =============================================================================


async def demo_device_info(ctx, slave_id):
    """Read and display V3 device information"""
    print("\n=== Device Info ===")

    sn = await ctx.get_device_sn(slave_id)
    print(f"  Serial Number: {sn}")

    fw = await ctx.get_device_fw_version(slave_id)
    print(f"  Firmware: {fw}")


async def demo_motor_status(ctx, slave_id):
    """Read and display motor status"""
    print("\n=== Motor Status ===")

    status = await ctx.v3_get_motor_status_data(slave_id)
    print(f"  Positions (first 5): {status.positions[:5]}")
    print(f"  Velocities (first 5): {status.velocities[:5]}")
    print(f"  Currents (first 5): {status.currents[:5]}")


async def demo_position_control(ctx, slave_id):
    """Single and batch motor position control"""
    print("\n=== Position Control ===")

    # Single motor
    print("  Motor 0 -> 45 degrees")
    await ctx.v3_set_motor_position(slave_id, 0, 45.0)
    await asyncio.sleep(0.5)

    # Read back
    positions = await ctx.v3_get_all_motor_positions(slave_id)
    print(f"  Positions (first 5): {[f'{p:.1f}' for p in positions[:5]]}")

    # Batch: all motors
    print("  All motors -> 30 degrees")
    target = [30.0] * REVO3_MOTOR_COUNT
    await ctx.v3_set_all_motor_positions(slave_id, target)
    await asyncio.sleep(1.0)

    # Open all
    print("  All motors -> 0 degrees")
    await ctx.v3_set_all_motor_positions(slave_id, [0.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.5)


async def demo_velocity_control(ctx, slave_id):
    """Single motor velocity control"""
    print("\n=== Velocity Control ===")

    print("  Motor 0 velocity -> 100")
    await ctx.v3_set_motor_velocity(slave_id, 0, 100.0)
    await asyncio.sleep(0.5)

    # Stop
    await ctx.v3_set_motor_velocity(slave_id, 0, 0.0)
    await asyncio.sleep(0.2)


async def demo_current_control(ctx, slave_id):
    """Single motor current control"""
    print("\n=== Current Control ===")

    print("  Motor 0 current -> 500 mA")
    await ctx.v3_set_motor_current(slave_id, 0, 500.0)
    await asyncio.sleep(0.5)

    # Stop
    await ctx.v3_set_motor_current(slave_id, 0, 0.0)
    await asyncio.sleep(0.2)


async def demo_status_monitor(ctx, slave_id, count=5):
    """Periodic status monitoring"""
    print(f"\n=== Status Monitor ({count} reads) ===")

    for i in range(count):
        status = await ctx.v3_get_motor_status_data(slave_id)
        pos_str = ", ".join(f"{p:.1f}" for p in status.positions[:5])
        print(f"  [{i}] pos: [{pos_str}]")
        await asyncio.sleep(0.2)


# =============================================================================
# Exclusive Demos
# =============================================================================


async def demo_new_single_joint(ctx, slave_id):
    """Single joint control"""
    print("\n=== Single Joint Control ===")
    print("  Registers: 1000 (joint_id) + 1001 (mode) + 1002 (param)")

    # Position mode: joint 0 -> 45 degrees (raw encoded)
    mode = sdk.V3ControlMode.Position
    print(f"  Joint 0: mode=Position({int(mode)}), param=45°")
    # Note: param is raw uint_to_float encoded value, use conversion as needed
    await ctx.revo3_single_joint_control(slave_id, 0, int(mode), 45)
    await asyncio.sleep(0.5)


async def demo_new_multi_joint(ctx, slave_id):
    """Multi-joint synchronous control"""
    print("\n=== Multi-Joint Synchronous Control ===")
    print("  Registers: 1010 (mode) + 1011~1031 (21 params)")

    mode = sdk.V3ControlMode.Position
    params = [30] * REVO3_MOTOR_COUNT  # 21 joints to 30° (raw)
    print(f"  All 21 joints: mode=Position, param=30°")
    await ctx.revo3_multi_joint_control(slave_id, int(mode), params)
    await asyncio.sleep(1.0)


async def demo_new_mit_control(ctx, slave_id):
    """MIT impedance control for single joint"""
    print("\n=== MIT Joint Control ===")
    print("  τ = Kp*(pos_ref − pos) + Kd*(vel_ref − vel) + τ_ff")
    print("  Registers: 1050~1055 (joint_id, kp, kd, pos, vel, torque_ff)")

    # Joint 0: Kp=5.0, Kd=0.5, pos=45°, vel=0, torque_ff=200mA
    print("  Joint 0: Kp=5.0, Kd=0.5, pos=45°, vel=0, τ_ff=200mA")
    await ctx.revo3_mit_control(slave_id, 0, 5.0, 0.5, 45.0, 0.0, 200.0)
    await asyncio.sleep(1.0)


async def demo_new_motor_params(ctx, slave_id):
    """Motor parameter configuration"""
    print("\n=== Motor Parameter Config ===")

    # Global protection current (mA)
    print("  Setting global protection current: 500 mA")
    await ctx.revo3_set_global_protect_current(slave_id, 500.0)
    await asyncio.sleep(0.1)

    # Per-joint protection current (mA)
    print("  Setting joint 0 protection current: 300 mA")
    await ctx.revo3_set_joint_protect_current(slave_id, 0, 300.0)
    await asyncio.sleep(0.1)

    print("  Motor parameter configuration done.")


async def demo_new_device_info(ctx, slave_id):
    """Device info and peripheral control"""
    print("\n=== Device Info & Peripherals ===")

    # Hardware version
    try:
        hw_ver = await ctx.revo3_get_hardware_version(slave_id)
        print(f"  Hardware Version: {hw_ver}")
    except Exception as e:
        print(f"  Hardware Version: (error: {e})")

    # Motor online status
    try:
        online = await ctx.revo3_get_motor_online_status(slave_id)
        online_count = bin(online).count("1")
        print(f"  Motor Online: 0x{online:06X} ({online_count}/21 online)")
    except Exception as e:
        print(f"  Motor Online: (error: {e})")


async def demo_new_teaching_mode(ctx, slave_id):
    """Teaching mode demo"""
    print("\n=== Teaching Mode ===")

    print("  Entering teaching mode...")
    await ctx.v3_set_teaching_mode(slave_id, True)
    await asyncio.sleep(1.0)

    print("  (In teaching mode, motors can be moved by hand)")
    print("  Exiting teaching mode...")
    await ctx.v3_set_teaching_mode(slave_id, False)
    await asyncio.sleep(0.5)


async def demo_new_peripherals(ctx, slave_id):
    """System peripheral control"""
    print("\n=== Peripheral Control ===")

    # Note: LED switch (reg 104) removed in V1.4

    # Touch screen
    print("  Touch screen on")
    await ctx.revo3_set_touch_screen(slave_id, True)
    await asyncio.sleep(0.3)


async def demo_new_multi_mit(ctx, slave_id):
    """Multi-joint MIT control (registers 1100–1204)"""
    print("\n=== Multi-Joint MIT Control ===")

    # Single joint via multi-MIT block
    print("  Joint 0 via multi-MIT: Kp=3.0, Kd=0.3, pos=30°, vel=0, τ_ff=100mA")
    await ctx.revo3_multi_mit_set_joint(slave_id, 0, 3.0, 0.3, 30.0, 0.0, 100.0)
    await asyncio.sleep(0.5)

    # All 21 joints
    print("  All 21 joints: Kp=2.0, Kd=0.2, pos=20°, vel=0, τ_ff=50mA")
    kp = [2.0] * REVO3_MOTOR_COUNT
    kd = [0.2] * REVO3_MOTOR_COUNT
    pos = [20.0] * REVO3_MOTOR_COUNT
    vel = [0.0] * REVO3_MOTOR_COUNT
    torque = [50.0] * REVO3_MOTOR_COUNT
    await ctx.revo3_multi_mit_set_all(slave_id, kp, kd, pos, vel, torque)
    await asyncio.sleep(1.0)


async def demo_new_batch_mit(ctx, slave_id):
    """MIT batch single-parameter control (registers 1300–1404)"""
    print("\n=== MIT Batch Parameter Control ===")

    print("  All Kp=4.0")
    await ctx.revo3_set_all_mit_kp(slave_id, [4.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    print("  All Kd=0.4")
    await ctx.revo3_set_all_mit_kd(slave_id, [0.4] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    print("  All positions=25°")
    await ctx.revo3_set_all_mit_positions(slave_id, [25.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    print("  All velocities=0")
    await ctx.revo3_set_all_mit_velocities(slave_id, [0.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    print("  All torques=100mA")
    await ctx.revo3_set_all_mit_torques(slave_id, [100.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.5)


async def demo_new_finger_control(ctx, slave_id):
    """Finger-level control (registers 1500–1574)"""
    print("\n=== Finger-Level Control ===")

    mode = int(sdk.V3ControlMode.Position)

    # Index finger (X100: 30° → 3000)
    print("  Index finger: mode=Position, params=[30, 30, 30, 30]°")
    await ctx.revo3_finger_control(slave_id, 1, mode, [3000, 3000, 3000, 3000])
    await asyncio.sleep(0.5)

    # Thumb (X100: 20° → 2000)
    print("  Thumb: mode=Position, params=[20, 20, 20, 20, 20]°")
    await ctx.revo3_thumb_control(slave_id, mode, [2000, 2000, 2000, 2000, 2000])
    await asyncio.sleep(0.5)


async def demo_new_motor_temps(ctx, slave_id):
    """Motor temperature monitoring"""
    print("\n=== Motor Temperatures ===")

    try:
        temps = await ctx.revo3_get_all_motor_temperatures(slave_id)
        temp_str = ", ".join([f"{t}" for t in temps[:5]])
        print(f"  Temperatures (first 5): [{temp_str}] °C")
    except Exception as e:
        print(f"  Temperatures: (error: {e})")

    try:
        temp = await ctx.revo3_get_motor_temperature(slave_id, 0)
        print(f"  Motor 0 temperature: {temp} °C")
    except Exception as e:
        print(f"  Motor 0 temperature: (error: {e})")


async def demo_new_motor_info(ctx, slave_id):
    """Motor SN and firmware versions"""
    print("\n=== Motor Info ===")

    try:
        sn = await ctx.revo3_get_motor_sn(slave_id, 0)
        print(f"  Motor 0 SN: {sn}")
    except Exception as e:
        print(f"  Motor 0 SN: (error: {e})")

    try:
        fw = await ctx.revo3_get_motor_fw_versions(slave_id)
        fw_str = ", ".join([str(v) for v in fw[:5]])
        print(f"  FW versions (first 5): [{fw_str}]")
    except Exception as e:
        print(f"  FW versions: (error: {e})")


async def main():
    device_ctx, extra_args, _ = await parse_args_and_init(sys.argv)
    if device_ctx is None:
        return

    ctx = device_ctx.ctx
    slave_id = device_ctx.slave_id

    # Verify V3 device
    if not ctx.uses_revo3_motor_api(slave_id):
        print(f"Warning: Device is not Revo3 (hw_type={device_ctx.hw_type})")
        print("V3 APIs may not work correctly on this device.")

    try:
        await demo_device_info(ctx, slave_id)
        await demo_motor_status(ctx, slave_id)
        await demo_position_control(ctx, slave_id)
        await demo_velocity_control(ctx, slave_id)
        await demo_current_control(ctx, slave_id)
        await demo_new_device_info(ctx, slave_id)
        await demo_new_single_joint(ctx, slave_id)
        await demo_new_multi_joint(ctx, slave_id)
        await demo_new_mit_control(ctx, slave_id)
        await demo_new_multi_mit(ctx, slave_id)
        await demo_new_batch_mit(ctx, slave_id)
        await demo_new_finger_control(ctx, slave_id)
        await demo_new_motor_temps(ctx, slave_id)
        await demo_new_motor_info(ctx, slave_id)
        await demo_new_motor_params(ctx, slave_id)
        await demo_new_teaching_mode(ctx, slave_id)
        await demo_new_peripherals(ctx, slave_id)
        await demo_status_monitor(ctx, slave_id)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await cleanup_context(device_ctx)
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
