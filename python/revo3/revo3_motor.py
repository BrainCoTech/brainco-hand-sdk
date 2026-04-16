"""
Revo3 (V3) Motor Control Example - 21 DoF Dexterous Hand

Demonstrates V3-specific motor control APIs:
  - Control modes: position, velocity, current, MIT impedance
  - Single motor and batch motor control
  - MIT mode: τ = Kp*(P_des - P_act) + Kd*(V_des - V_act) + T_ff
  - Motor status monitoring
  - Single/multi joint control with V3ControlMode
  - MIT joint control (single, multi-joint, batch)
  - Finger-level and thumb control
  - Motor temperature monitoring
  - Motor SN and firmware version reading
  - Motor parameter config (protection current)
  - Hardware version, motor online status, teaching mode

Usage:
    python revo3_motor.py
    python revo3_motor.py --port /dev/ttyUSB0
"""

import asyncio
import sys
import argparse
from revo3_utils import *


async def main(port_name=None):
    """Main function: Initialize Revo3 and execute control examples"""
    # Connect to Revo3 device
    (client, slave_id) = await open_modbus_revo3(port_name=port_name)

    await demo_device_info(client, slave_id)
    await demo_motor_status(client, slave_id)
    await demo_position_control(client, slave_id)
    await demo_velocity_control(client, slave_id)
    await demo_current_control(client, slave_id)
    await demo_new_device_info(client, slave_id)
    await demo_new_single_joint(client, slave_id)
    await demo_new_multi_joint(client, slave_id)
    await demo_new_mit_control(client, slave_id)
    await demo_new_multi_mit(client, slave_id)
    await demo_new_batch_mit(client, slave_id)
    await demo_new_finger_control(client, slave_id)
    await demo_new_finger_mit(client, slave_id)
    await demo_new_impedance_damping(client, slave_id)
    await demo_new_motor_temps(client, slave_id)
    await demo_new_motor_info(client, slave_id)
    await demo_new_motor_params(client, slave_id)
    await demo_new_teaching_mode(client, slave_id)
    await demo_status_monitor(client, slave_id, count=5)

    # Cleanup
    libstark.modbus_close(client)
    logger.info("Done. Closed.")


# =============================================================================
# Demo Functions
# =============================================================================


async def demo_device_info(client, slave_id):
    """Read and display device information"""
    logger.info("=== Device Info ===")

    device_info = await client.get_device_info(slave_id)
    logger.info(f"  Serial Number: {device_info.serial_number}")
    logger.info(f"  Firmware: {device_info.firmware_version}")
    logger.info(f"  Hardware: {device_info.hardware_type}")
    logger.info(f"  SKU: {device_info.sku_type}")


async def demo_motor_status(client, slave_id):
    """Read motor status"""
    logger.info("=== Motor Status ===")

    status = await client.v3_get_motor_status_data(slave_id)
    logger.info(f"  Positions (first 5): {status.positions[:5]}")
    logger.info(f"  Velocities (first 5): {status.velocities[:5]}")
    logger.info(f"  Currents (first 5): {status.currents[:5]}")


async def demo_position_control(client, slave_id):
    """Position control demo"""
    logger.info("=== Position Control ===")

    # Single motor position
    logger.info("  Motor 0 -> 45 degrees")
    await client.v3_set_motor_position(slave_id, 0, 45.0)
    await asyncio.sleep(0.5)

    # Read back
    positions = await client.v3_get_all_motor_positions(slave_id)
    logger.info(f"  Positions (first 5): {[f'{p:.1f}' for p in positions[:5]]}")

    # Batch: all motors to 30 degrees
    logger.info("  All motors -> 30 degrees")
    target = [30.0] * REVO3_MOTOR_COUNT
    await client.v3_set_all_motor_positions(slave_id, target)
    await asyncio.sleep(1.0)

    # Open all
    logger.info("  All motors -> 0 degrees")
    target = [0.0] * REVO3_MOTOR_COUNT
    await client.v3_set_all_motor_positions(slave_id, target)
    await asyncio.sleep(0.5)


async def demo_velocity_control(client, slave_id):
    """Velocity control demo"""
    logger.info("=== Velocity Control ===")

    logger.info("  Motor 0 velocity -> 100")
    await client.v3_set_motor_velocity(slave_id, 0, 100.0)
    await asyncio.sleep(0.5)

    # Stop
    await client.v3_set_motor_velocity(slave_id, 0, 0.0)
    await asyncio.sleep(0.2)


async def demo_current_control(client, slave_id):
    """Current control demo"""
    logger.info("=== Current Control ===")

    logger.info("  Motor 0 current -> 500 mA")
    await client.v3_set_motor_current(slave_id, 0, 500.0)
    await asyncio.sleep(0.5)

    # Stop
    await client.v3_set_motor_current(slave_id, 0, 0.0)
    await asyncio.sleep(0.2)


async def demo_status_monitor(client, slave_id, count=5):
    """Periodic status monitoring"""
    logger.info(f"=== Status Monitor ({count} reads) ===")

    for i in range(count):
        status = await client.v3_get_motor_status_data(slave_id)
        pos_str = " ".join([f"{p:.1f}" for p in status.positions[:5]])
        logger.info(f"  [{i}] pos: {pos_str}")
        await asyncio.sleep(0.2)


# =============================================================================
# Revo3 Demos
# =============================================================================

async def demo_new_device_info(client, slave_id):
    """Device info and motor online status"""
    logger.info("=== [New] Device Info ===")

    try:
        hw_ver = await client.revo3_get_hardware_version(slave_id)
        logger.info(f"  Hardware Version: {hw_ver}")
    except Exception as e:
        logger.info(f"  Hardware Version: (error: {e})")

    try:
        online = await client.revo3_get_motor_online_status(slave_id)
        online_count = bin(online).count("1")
        logger.info(f"  Motor Online: 0x{online:06X} ({online_count}/21 online)")
    except Exception as e:
        logger.info(f"  Motor Online: (error: {e})")


async def demo_new_single_joint(client, slave_id):
    """Single joint control"""
    logger.info("=== [New] Single Joint Control ===")

    mode = libstark.V3ControlMode.Position
    logger.info(f"  Joint 0: mode=Position({int(mode)}), param=45°")
    await client.revo3_single_joint_control(slave_id, 0, int(mode), 45)
    await asyncio.sleep(0.5)


async def demo_new_multi_joint(client, slave_id):
    """Multi-joint synchronous control"""
    logger.info("=== [New] Multi-Joint Control ===")

    mode = libstark.V3ControlMode.Position
    params = [30] * REVO3_MOTOR_COUNT  # 21 joints to 30° (raw)
    logger.info(f"  All 21 joints: mode=Position, param=30°")
    await client.revo3_multi_joint_control(slave_id, int(mode), params)
    await asyncio.sleep(1.0)


async def demo_new_mit_control(client, slave_id):
    """MIT impedance control for single joint"""
    logger.info("=== [New] MIT Joint Control ===")
    logger.info("  τ = Kp*(pos_ref − pos) + Kd*(vel_ref − vel) + τ_ff")

    logger.info("  Joint 0: Kp=5.0, Kd=0.5, pos=45°, vel=0, τ_ff=200mA")
    await client.revo3_mit_control(slave_id, 0, 5.0, 0.5, 45.0, 0.0, 200.0)
    await asyncio.sleep(1.0)


async def demo_new_multi_mit(client, slave_id):
    """Multi-joint MIT control (registers 1100–1204)"""
    logger.info("=== [New] Multi-Joint MIT Control ===")

    # Single joint via multi-MIT block
    logger.info("  Joint 0 via multi-MIT: Kp=3.0, Kd=0.3, pos=30°, vel=0, τ_ff=100mA")
    await client.revo3_multi_mit_set_joint(slave_id, 0, 3.0, 0.3, 30.0, 0.0, 100.0)
    await asyncio.sleep(0.5)

    # All 21 joints via multi-MIT block
    logger.info("  All 21 joints via multi-MIT: Kp=2.0, Kd=0.2, pos=20°")
    kp = [2.0] * REVO3_MOTOR_COUNT
    kd = [0.2] * REVO3_MOTOR_COUNT
    pos = [20.0] * REVO3_MOTOR_COUNT
    vel = [0.0] * REVO3_MOTOR_COUNT
    torque = [50.0] * REVO3_MOTOR_COUNT
    await client.revo3_multi_mit_set_all(slave_id, kp, kd, pos, vel, torque)
    await asyncio.sleep(1.0)


async def demo_new_batch_mit(client, slave_id):
    """MIT batch single-parameter control (registers 1300–1404)"""
    logger.info("=== [New] MIT Batch Parameter Control ===")

    logger.info("  All Kp=4.0")
    await client.revo3_set_all_mit_kp(slave_id, [4.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    logger.info("  All Kd=0.4")
    await client.revo3_set_all_mit_kd(slave_id, [0.4] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    logger.info("  All positions=25°")
    await client.revo3_set_all_mit_positions(slave_id, [25.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    logger.info("  All velocities=0")
    await client.revo3_set_all_mit_velocities(slave_id, [0.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.1)

    logger.info("  All torques=100mA")
    await client.revo3_set_all_mit_torques(slave_id, [100.0] * REVO3_MOTOR_COUNT)
    await asyncio.sleep(0.5)


async def demo_new_finger_control(client, slave_id):
    """Finger-level control (registers 1500–1574)"""
    logger.info("=== [New] Finger-Level Control ===")

    mode = int(libstark.V3ControlMode.Position)

    # Index finger position control (X100: 30° → 3000)
    logger.info(f"  Index finger: mode=Position, params=[30, 30, 30, 30]°")
    params = [3000, 3000, 3000, 3000]
    await client.revo3_finger_control(slave_id, 1, mode, params)
    await asyncio.sleep(0.5)

    # Thumb control (X100: 20° → 2000)
    logger.info(f"  Thumb: mode=Position, params=[20, 20, 20, 20, 20]°")
    params = [2000, 2000, 2000, 2000, 2000]
    await client.revo3_thumb_control(slave_id, mode, params)
    await asyncio.sleep(0.5)


async def demo_new_finger_mit(client, slave_id):
    """Finger MIT and Thumb MIT control (registers 1520–1574)"""
    logger.info("=== [New] Finger/Thumb MIT Control ===")

    # Finger MIT: Index finger (finger_id=1), 4 joints × 5 params
    logger.info("  Index finger MIT: Kp=2.0, Kd=0.2, pos=30°, vel=0, τ_ff=100mA")
    # 4 joints: [kp, kd, pos, vel, τ_ff] × 4
    finger_params = []
    for _ in range(4):
        finger_params.extend([2.0, 0.2, 30.0, 0.0, 100.0])
    await client.revo3_finger_mit_control(slave_id, 1, finger_params)
    await asyncio.sleep(0.5)

    # Thumb MIT: 5 joints × 5 params
    logger.info("  Thumb MIT: Kp=1.5, Kd=0.15, pos=20°, vel=0, τ_ff=50mA")
    thumb_params = []
    for _ in range(5):
        thumb_params.extend([1.5, 0.15, 20.0, 0.0, 50.0])
    await client.revo3_thumb_mit_control(slave_id, thumb_params)
    await asyncio.sleep(0.5)


async def demo_new_impedance_damping(client, slave_id):
    """Impedance and Damping mode control"""
    logger.info("=== [New] Impedance & Damping Mode ===")

    # Impedance mode (V3ControlMode=4), param = coefficient × 100, range 0-100
    logger.info("  Joint 0: Impedance mode, coefficient=50")
    await client.revo3_single_joint_control(slave_id, 0, 4, 5000)  # 50 × 100
    await asyncio.sleep(0.5)

    # Damping mode (V3ControlMode=5), param = coefficient × 100, range 0-100
    logger.info("  Joint 0: Damping mode, coefficient=30")
    await client.revo3_single_joint_control(slave_id, 0, 5, 3000)  # 30 × 100
    await asyncio.sleep(0.5)

    # Multi-joint impedance
    logger.info("  All 21 joints: Impedance mode, coefficient=40")
    params = [4000] * 21  # 40 × 100 for all joints
    await client.revo3_multi_joint_control(slave_id, 4, params)
    await asyncio.sleep(0.5)

    # Reset to position mode
    logger.info("  Reset: All 21 joints -> Position mode, 0°")
    await client.revo3_multi_joint_control(slave_id, 0, [0] * 21)
    await asyncio.sleep(0.5)


async def demo_new_motor_temps(client, slave_id):
    """Motor temperature monitoring"""
    logger.info("=== [New] Motor Temperatures ===")

    try:
        temps = await client.revo3_get_all_motor_temperatures(slave_id)
        temp_str = ", ".join([f"{t}" for t in temps[:5]])
        logger.info(f"  Temperatures (first 5): [{temp_str}] °C")
    except Exception as e:
        logger.info(f"  Temperatures: (error: {e})")

    try:
        temp = await client.revo3_get_motor_temperature(slave_id, 0)
        logger.info(f"  Motor 0 temperature: {temp} °C")
    except Exception as e:
        logger.info(f"  Motor 0 temperature: (error: {e})")


async def demo_new_motor_info(client, slave_id):
    """Motor SN and firmware version"""
    logger.info("=== [New] Motor Info ===")

    try:
        sn = await client.revo3_get_motor_sn(slave_id, 0)
        logger.info(f"  Motor 0 SN: {sn}")
    except Exception as e:
        logger.info(f"  Motor 0 SN: (error: {e})")

    try:
        fw_versions = await client.revo3_get_motor_fw_versions(slave_id)
        fw_str = ", ".join([str(v) for v in fw_versions[:5]])
        logger.info(f"  FW versions (first 5): [{fw_str}]")
    except Exception as e:
        logger.info(f"  FW versions: (error: {e})")


async def demo_new_motor_params(client, slave_id):
    """Motor parameter configuration"""
    logger.info("=== [New] Motor Parameters ===")

    logger.info("  Setting global protection current: 500 mA")
    await client.revo3_set_global_protect_current(slave_id, 500.0)
    await asyncio.sleep(0.1)

    logger.info("  Setting joint 0 protection current: 300 mA")
    await client.revo3_set_joint_protect_current(slave_id, 0, 300.0)
    await asyncio.sleep(0.1)


async def demo_new_teaching_mode(client, slave_id):
    """Teaching mode"""
    logger.info("=== [New] Teaching Mode ===")

    logger.info("  Entering teaching mode...")
    await client.v3_set_teaching_mode(slave_id, True)
    await asyncio.sleep(1.0)

    logger.info("  (Motors can be moved by hand)")
    logger.info("  Exiting teaching mode...")
    await client.v3_set_teaching_mode(slave_id, False)
    await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Motor Control Example")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port name")
    args = parser.parse_args()

    try:
        asyncio.run(main(port_name=args.port))
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
