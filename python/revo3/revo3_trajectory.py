"""
Revo3 Trajectory Control & Teaching Mode Example

Demonstrates the high-level trajectory and teaching APIs:
  - move_joint: quintic polynomial trajectory for a single joint
  - move_hand: synchronized multi-joint trajectory
  - teach_joint: backdrive recording for a single joint
  - teach_hand: full-hand backdrive recording
  - replay_joint / replay_hand: playback recorded trajectories
  - Position range protection

Usage:
    python revo3_trajectory.py
    python revo3_trajectory.py --port /dev/ttyUSB0
"""

import asyncio
import sys
import argparse
from revo3_utils import *


async def main(port_name=None):
    """Main function: Initialize Revo3 and execute trajectory demos"""
    (client, slave_id) = await open_modbus_revo3(port_name=port_name)

    await demo_single_joint_move(client, slave_id)
    await demo_single_joint_custom_gains(client, slave_id)
    await demo_single_joint_move_with_speed(client, slave_id)
    await demo_full_hand_move(client, slave_id)
    await demo_full_hand_move_with_speed(client, slave_id)
    await demo_position_protection(client, slave_id)
    await demo_teach_and_replay_joint(client, slave_id)
    await demo_teach_and_replay_hand(client, slave_id)

    # Cleanup
    libstark.modbus_close(client)
    logger.info("Done. Closed.")


# =============================================================================
# Trajectory Control Demos
# =============================================================================


async def demo_single_joint_move(client, slave_id):
    """Single joint quintic polynomial move"""
    logger.info("=== Single Joint Move (Quintic Polynomial) ===")

    joint_id = 3  # Pinky DIP (top joint) [0, 90°]
    target = 45.0
    duration = 2.0
    dt = 0.01  # 100Hz control

    # Read initial position
    status = await client.revo3_get_motor_status_data(slave_id)
    logger.info(f"  J{joint_id} initial: {status.positions[joint_id]:.2f}°")

    logger.info(f"  Moving J{joint_id} to {target}° over {duration}s...")
    await client.revo3_move_joint(slave_id, joint_id, target, duration, dt)

    # Verify
    await asyncio.sleep(0.2)
    status = await client.revo3_get_motor_status_data(slave_id)
    final_pos = status.positions[joint_id]
    error = abs(target - final_pos)
    logger.info(f"  Final: {final_pos:.2f}° (error: {error:.2f}°) {'✅' if error < 5.0 else '⚠️'}")

    # Move back
    logger.info(f"  Moving J{joint_id} back to 0°...")
    await client.revo3_move_joint(slave_id, joint_id, 0.0, duration, dt)
    await asyncio.sleep(0.5)


async def demo_single_joint_custom_gains(client, slave_id):
    """Single joint move with custom Kp/Kd"""
    logger.info("\n=== Single Joint Move with Custom Gains ===")

    joint_id = 1  # Pinky MCP [0, 90°]
    target = 60.0
    kp, kd = 5.0, 0.5

    logger.info(f"  J{joint_id}: target={target}°, Kp={kp}, Kd={kd}, T=1.5s")
    await client.revo3_move_joint_with_gains(slave_id, joint_id, target, 1.5, 0.01, kp, kd)

    await asyncio.sleep(0.2)
    status = await client.revo3_get_motor_status_data(slave_id)
    logger.info(f"  Final: {status.positions[joint_id]:.2f}°")

    # Move back
    await client.revo3_move_joint(slave_id, joint_id, 0.0, 1.5, 0.01)
    await asyncio.sleep(0.5)


async def demo_single_joint_move_with_speed(client, slave_id):
    """Single joint move with specified speed"""
    logger.info("\n=== Single Joint Move with Speed ===")

    joint_id = 3  # Pinky DIP
    target = 45.0
    speed = 30.0  # 30 rpm

    logger.info(f"  J{joint_id}: target={target}°, speed={speed} rpm")
    await client.revo3_move_joint_with_speed(slave_id, joint_id, target, speed, 0.01)

    await asyncio.sleep(0.2)
    status = await client.revo3_get_motor_status_data(slave_id)
    logger.info(f"  Final: {status.positions[joint_id]:.2f}°")

    # Move back
    logger.info(f"  Moving J{joint_id} back to 0° at {speed} rpm...")
    await client.revo3_move_joint_with_speed(slave_id, joint_id, 0.0, speed, 0.01)
    await asyncio.sleep(0.5)


async def demo_full_hand_move(client, slave_id):
    """Full hand synchronized move"""
    logger.info("\n=== Full Hand Move (21 joints) ===")

    # Move MCP joints to 45°, others stay at 0°
    targets = [0.0] * REVO3_MOTOR_COUNT
    mcp_joints = [1, 5, 9, 13, 17]  # MCP joints for each finger
    for jid in mcp_joints:
        targets[jid] = 45.0

    logger.info(f"  MCP joints {mcp_joints} → 45°, T=3.0s")
    await client.revo3_move_hand(slave_id, targets, 3.0, 0.01)

    # Verify
    await asyncio.sleep(0.5)
    status = await client.revo3_get_motor_status_data(slave_id)
    logger.info("  Final MCP positions:")
    for jid in mcp_joints:
        pos = status.positions[jid]
        err = abs(targets[jid] - pos)
        logger.info(f"    J{jid:>2}: {pos:.2f}° (err={err:.2f}°) {'✅' if err < 5.0 else '⚠️'}")

    # Reset
    logger.info("  Resetting all to 0°...")
    await client.revo3_move_hand(slave_id, [0.0] * REVO3_MOTOR_COUNT, 3.0, 0.01)
    await asyncio.sleep(0.5)


async def demo_full_hand_move_with_speed(client, slave_id):
    """Full hand synchronized move with uniform speed"""
    logger.info("\n=== Full Hand Move with Uniform Speed ===")

    # Move PIP joints to 60°, others stay at 0°
    targets = [0.0] * REVO3_MOTOR_COUNT
    pip_joints = [2, 6, 10, 14, 18]  # PIP joints for each finger
    for jid in pip_joints:
        targets[jid] = 60.0

    speed = 20.0  # 20 rpm
    logger.info(f"  PIP joints {pip_joints} → 60°, speed={speed} rpm")
    await client.revo3_move_hand_with_speed(slave_id, targets, speed, 0.01)

    # Verify
    await asyncio.sleep(0.5)
    status = await client.revo3_get_motor_status_data(slave_id)
    logger.info("  Final PIP positions:")
    for jid in pip_joints:
        pos = status.positions[jid]
        err = abs(targets[jid] - pos)
        logger.info(f"    J{jid:>2}: {pos:.2f}° (err={err:.2f}°) {'✅' if err < 5.0 else '⚠️'}")

    # Reset
    logger.info(f"  Resetting all to 0° at {speed} rpm...")
    await client.revo3_move_hand_with_speed(slave_id, [0.0] * REVO3_MOTOR_COUNT, speed, 0.01)
    await asyncio.sleep(0.5)


async def demo_position_protection(client, slave_id):
    """Test position range protection"""
    logger.info("\n=== Position Range Protection ===")

    # J0 (Pinky Abd, range [-14, 15]) to 50° — should fail
    logger.info("  J0 (Pinky Abd) → 50° (range: [-14, 15])...")
    try:
        await client.revo3_move_joint(slave_id, 0, 50.0, 1.0, 0.01)
        logger.info("  ⚠️ Command accepted (unexpected)")
    except Exception as e:
        logger.info(f"  ✅ Correctly rejected: {e}")

    # J20 (Thumb CMC Flex, range [0, 75]) to -10° — should fail
    logger.info("  J20 (Thumb CMC Flex) → -10° (range: [0, 75])...")
    try:
        await client.revo3_move_joint(slave_id, 20, -10.0, 1.0, 0.01)
        logger.info("  ⚠️ Command accepted (unexpected)")
    except Exception as e:
        logger.info(f"  ✅ Correctly rejected: {e}")


# =============================================================================
# Teaching Mode Demos
# =============================================================================


async def demo_teach_and_replay_joint(client, slave_id):
    """Single joint teaching and replay"""
    logger.info("\n=== Single Joint Teaching & Replay ===")

    joint_id = 3  # Pinky DIP
    dt = 0.02       # 50 Hz recording
    duration = 5.0

    logger.info(f"  Teaching J{joint_id}: move the joint freely for {duration}s...")
    logger.info("  Recording starts NOW!")

    recorded = await client.revo3_teach_joint(slave_id, joint_id, dt, duration)

    # Summary
    if recorded:
        min_pos = min(recorded)
        max_pos = max(recorded)
        logger.info(f"\n  Recorded {len(recorded)} samples")
        logger.info(f"  Range: {min_pos:.2f}° .. {max_pos:.2f}°")
        logger.info(f"  Start: {recorded[0]:.2f}°, End: {recorded[-1]:.2f}°")

        # Print a few samples
        step = max(1, len(recorded) // 8)
        logger.info("\n    Time(s) | Position(°)")
        logger.info("    --------|------------")
        for i in range(0, len(recorded), step):
            logger.info(f"    {i * dt:>6.2f}  | {recorded[i]:>8.2f}")

    # Replay
    logger.info(f"\n  Replaying {len(recorded)} samples...")
    await asyncio.sleep(2.0)
    await client.revo3_replay_joint(slave_id, joint_id, recorded, dt, 3.0, 0.3)
    logger.info("  Replay complete!")

    # Reset
    await client.revo3_move_joint(slave_id, joint_id, 0.0, 2.0, 0.01)
    await asyncio.sleep(0.5)


async def demo_teach_and_replay_hand(client, slave_id):
    """Full hand teaching and replay"""
    logger.info("\n=== Full Hand Teaching & Replay ===")

    dt = 0.02       # 50 Hz
    duration = 5.0

    logger.info(f"  Teaching all joints: move the hand freely for {duration}s...")
    logger.info("  Recording starts NOW!")

    trajectory = await client.revo3_teach_hand(slave_id, dt, duration)

    # Summary
    if trajectory:
        logger.info(f"\n  Recorded {len(trajectory)} frames ({len(trajectory) * dt:.1f}s)")

        # Show start vs end for key joints
        first = trajectory[0]
        last = trajectory[-1]
        mcp_joints = {"Pinky": 1, "Ring": 5, "Mid": 9, "Index": 13, "Thumb": 17}
        logger.info("\n    Joint     | Start(°) | End(°)  | Delta(°)")
        logger.info("    ----------|----------|---------|----------")
        for name, jid in mcp_joints.items():
            s, e = first[jid], last[jid]
            logger.info(f"    J{jid:>2} {name:<6}| {s:>7.2f}  | {e:>6.2f}  | {e - s:>+7.2f}")

    # Replay
    logger.info(f"\n  Replaying {len(trajectory)} frames...")
    await asyncio.sleep(2.0)
    await client.revo3_replay_hand(slave_id, trajectory, dt, 3.0, 0.3)
    logger.info("  Replay complete!")

    # Reset
    logger.info("  Resetting to 0°...")
    await client.revo3_move_hand(slave_id, [0.0] * REVO3_MOTOR_COUNT, 3.0, 0.01)
    await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Trajectory Control Example")
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
