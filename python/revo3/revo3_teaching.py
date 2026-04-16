"""
Revo3 Teaching Mode Demo

Record hand movements in zero-torque mode, then play them back.
Designed for pen-spinning and other manipulation demos.

Workflow:
  1. RECORD: Set all MIT params (kp, kd, pos, vel, current) to 0,
             making the hand compliant (free to move by hand).
             Record motor positions at high frequency.
  2. STOP:   Restore original control and save recorded trajectory.
  3. PLAY:   Replay the recorded trajectory with position control.

Usage:
    python revo3_teaching.py                          # Interactive mode
    python revo3_teaching.py --port /dev/ttyUSB0      # Specify port
    python revo3_teaching.py --freq 100               # Recording freq (Hz)
    python revo3_teaching.py --save trajectory.json   # Save to file
    python revo3_teaching.py --load trajectory.json   # Load and play
    python revo3_teaching.py --speed 0.5              # Playback at 0.5x speed
    python revo3_teaching.py --speed 2.0              # Playback at 2.0x speed
    python revo3_teaching.py --loop 3                 # Playback 3 times
"""

import asyncio
import sys
import time
import json
import platform
import argparse
from common_imports import modbus_open
from revo3_utils import *


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_RECORD_FREQ = 100    # Hz - recording frequency
DEFAULT_PLAYBACK_SPEED = 1.0  # 1.0 = real-time
DEFAULT_LOOP_COUNT = 1        # Number of playback loops
COLLECTOR_FREQ = 200          # DataCollector polling (macOS safe)
COLLECTOR_FREQ_LINUX = 2000   # DataCollector polling (Linux)

# Motor indices for display grouping
MOTOR_LABELS = {
    "Pinky":  [0, 1, 2, 3],
    "Ring":   [4, 5, 6, 7],
    "Middle": [8, 9, 10, 11],
    "Index":  [12, 13, 14, 15],
    "Thumb":  [16, 17, 18, 19, 20],
    "Wrist":  [21, 22],
}


# =============================================================================
# Trajectory Data
# =============================================================================

class Trajectory:
    """Stores a sequence of timestamped motor position snapshots."""

    def __init__(self):
        self.frames = []       # List of (timestamp_sec, positions[23])
        self.start_time = None

    def add_frame(self, positions):
        """Add a position snapshot with relative timestamp."""
        now = time.perf_counter()
        if self.start_time is None:
            self.start_time = now
        relative_t = now - self.start_time
        # Copy positions list
        self.frames.append((relative_t, list(positions)))

    @property
    def duration(self):
        if not self.frames:
            return 0.0
        return self.frames[-1][0]

    @property
    def frame_count(self):
        return len(self.frames)

    def save(self, filepath):
        """Save trajectory to JSON file."""
        actual_motor_count = len(self.frames[0][1]) if self.frames else 0
        data = {
            "motor_count": actual_motor_count,
            "frame_count": len(self.frames),
            "duration_sec": self.duration,
            "protocol": "new",
            "frames": [
                {"t": round(t, 4), "pos": [round(p, 2) for p in pos]}
                for t, pos in self.frames
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Trajectory saved: {filepath} ({len(self.frames)} frames, {self.duration:.2f}s)")

    @staticmethod
    def load(filepath):
        """Load trajectory from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        traj = Trajectory()
        traj.start_time = 0  # Already has relative timestamps
        traj.recorded_protocol = data.get("protocol", "unknown")
        for frame in data["frames"]:
            traj.frames.append((frame["t"], frame["pos"]))
        logger.info(f"Trajectory loaded: {filepath} "
                   f"({traj.frame_count} frames, {traj.duration:.2f}s, "
                   f"protocol={traj.recorded_protocol}, pos_per_frame={len(data['frames'][0]['pos'])})")
        return traj

    def summary(self):
        """Print trajectory summary."""
        if not self.frames:
            logger.info("  (empty trajectory)")
            return
        logger.info(f"  Frames: {self.frame_count}")
        logger.info(f"  Duration: {self.duration:.2f}s")
        avg_freq = self.frame_count / self.duration if self.duration > 0 else 0
        logger.info(f"  Avg frequency: {avg_freq:.1f} Hz")

        # Show position range per finger group
        all_pos = [pos for _, pos in self.frames]
        pos_len = len(all_pos[0]) if all_pos else 0
        for name, motor_ids in MOTOR_LABELS.items():
            # Skip motors beyond the recorded position count
            valid_ids = [mid for mid in motor_ids if mid < pos_len]
            if not valid_ids:
                continue
            mins = [min(frame[mid] for frame in all_pos) for mid in valid_ids]
            maxs = [max(frame[mid] for frame in all_pos) for mid in valid_ids]
            ranges = [f"M{mid}:[{mn:.0f}°,{mx:.0f}°]" for mid, mn, mx in zip(valid_ids, mins, maxs)]
            logger.info(f"  {name:6s}: {', '.join(ranges)}")


# =============================================================================
# Teaching Mode (Record)
# =============================================================================

async def enter_teaching_mode(client, slave_id):
    """Enter teaching mode - hand becomes compliant (zero torque).

    Revo3:  Uses dedicated teaching mode register (register 118).
    """
    logger.info("Entering teaching mode (zero-torque)...")

    if True:
        # Explicitly set Impedance mode and zero stiffness
        try:
            await client.v3_set_ctrl_mode_all(slave_id, 4)  # 4 = Impedance Mode
            await asyncio.sleep(0.1)
            zeros = [0.0] * 21
            pos = await client.v3_get_all_motor_positions(slave_id)
            pos = pos[:21] if pos and len(pos) >= 21 else list(zeros)
            await client.revo3_set_all_mit_batch(
                slave_id,
                zeros,  # Kp
                zeros,  # Kd
                pos,    # Position
                zeros,  # Velocity
                zeros   # Torque FF
            )
        except Exception as e:
            logger.debug(f"Revo3 MIT zeroing skipped: {e}")

    else:
        # zero all MIT impedance params
        zeros = [0.0] * REVO3_MOTOR_COUNT
        await client.v3_set_all_motor_mit(
            slave_id,
            zeros,   # velocities
            zeros,   # positions
            zeros,   # currents (torque feedforward)
            zeros,   # kp
            zeros,   # kd
        )

    logger.info("✅ Teaching mode active - hand is compliant, move fingers freely")


async def exit_teaching_mode(client, slave_id, restore_positions=None):
    """Exit teaching mode and restore motor control.

    Method 1: Disables teaching mode register, then sends position targets.
    Method 2: Directly sends position targets (overrides MIT zero state).
    """
    logger.info("Exiting teaching mode...")

    if True:
        # Workaround: switch back to Position mode (0) to restore internal PID stiffness
        try:
            await client.v3_set_ctrl_mode_all(slave_id, 0)
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.debug(f"restore position mode skipped: {e}")

        if restore_positions is not None:
            await client.v3_set_all_motor_positions(slave_id, restore_positions)
            logger.info(f"✅ Restored to initial positions")
        else:
            target = [0.0] * REVO3_MOTOR_COUNT
            await client.v3_set_all_motor_positions(slave_id, target)
            logger.info(f"✅ Reset to zero position")
    else:
        # restore Kp/Kd to recover positional rigidity
        # (they were zeroed during teaching mode)
        target = restore_positions if restore_positions else [0.0] * REVO3_MOTOR_COUNT
        kps = [0.8] * REVO3_MOTOR_COUNT
        kds = [0.01] * REVO3_MOTOR_COUNT
        zeros = [0.0] * REVO3_MOTOR_COUNT
        await client.v3_set_all_motor_mit(slave_id, zeros, target, zeros, kps, kds)
        logger.info(f"✅ Restored rigidity and initial positions")
        logger.info("✅ Motors returned to zero position")

    await asyncio.sleep(0.5)


async def record_trajectory(client, slave_id, motor_buffer, record_freq, result_holder):
    """Record motor positions in teaching mode.

    Args:
        client: Modbus client
        slave_id: Device slave ID
        motor_buffer: V3MotorStatusBuffer for reading positions
        record_freq: Target recording frequency in Hz
        result_holder: dict with key 'trajectory' to store result (survives cancellation)
    """
    trajectory = Trajectory()
    result_holder['trajectory'] = trajectory  # Share reference so caller can access it
    interval = 1.0 / record_freq

    logger.info(f"📝 Recording at {record_freq} Hz... (Press Enter to stop)")
    logger.info("   Move the fingers now!")

    frame_count = 0
    last_print_time = time.perf_counter()

    try:
        while True:
            loop_start = time.perf_counter()

            # Read current motor positions
            latest = motor_buffer.peek_latest()
            if latest and hasattr(latest, 'positions'):
                positions = list(latest.positions)
                trajectory.add_frame(positions)
                frame_count += 1

                # Print progress every 2 seconds
                now = time.perf_counter()
                if now - last_print_time >= 2.0:
                    elapsed = trajectory.duration
                    actual_freq = frame_count / elapsed if elapsed > 0 else 0
                    # Show first 5 motor positions as preview
                    pos_preview = " ".join([f"{positions[i]:6.1f}" for i in range(5)])
                    logger.info(f"  [{elapsed:.1f}s] {frame_count} frames ({actual_freq:.0f}Hz) "
                               f"| M0-4: {pos_preview}")
                    last_print_time = now

            # Maintain target frequency
            elapsed_loop = time.perf_counter() - loop_start
            sleep_time = interval - elapsed_loop
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        pass

    logger.info(f"⏹ Recording stopped: {trajectory.frame_count} frames, {trajectory.duration:.2f}s")


# =============================================================================
# Playback
# =============================================================================

async def playback_trajectory(client, slave_id, trajectory, speed=1.0, motor_buffer=None):
    """Play back a recorded trajectory using position control.

    Args:
        client: Modbus client
        slave_id: Device slave ID
        trajectory: Trajectory to play back
        speed: Playback speed multiplier (1.0 = real-time, 0.5 = half speed, 2.0 = double)
        motor_buffer: Optional, for monitoring actual positions during playback
    """
    if trajectory.frame_count < 2:
        logger.warning("Trajectory too short to play back (need >= 2 frames)")
        return

    logger.info(f"▶ Playing back {trajectory.frame_count} frames "
               f"({trajectory.duration:.2f}s at {speed:.1f}x speed)...")

    # Log first frame to verify data is reasonable
    first_pos = trajectory.frames[0][1]
    pos_preview = " ".join([f"{first_pos[j]:6.1f}" for j in range(min(5, len(first_pos)))])
    logger.info(f"  First frame M0-4: {pos_preview}")

    # --- MUST INITIALIZE RIGIDITY BEFORE PLAYBACK ---
    if True:
        try:
            # Ensure it is in Position Control mode
            await client.v3_set_ctrl_mode_all(slave_id, 0)
            await asyncio.sleep(0.1)
        except Exception:
            pass
    else:
        # If the user ran --load right after recording without power cycling,
        # Kp and Kd might still be 0! We MUST explicitly restore them.
        zeros = [0.0] * REVO3_MOTOR_COUNT
        kps = [0.8] * REVO3_MOTOR_COUNT
        kds = [0.01] * REVO3_MOTOR_COUNT

        pos_init = list(first_pos)
        while len(pos_init) < REVO3_MOTOR_COUNT:
            pos_init.append(0.0)

        await client.v3_set_all_motor_mit(slave_id, zeros, pos_init, zeros, kps, kds)
        await asyncio.sleep(0.1)

    playback_start = time.perf_counter()
    frame_idx = 0
    last_print_time = playback_start

    try:
        for i, (target_t, positions) in enumerate(trajectory.frames):
            # Adjust timestamp for playback speed
            adjusted_t = target_t / speed

            # Wait until it's time for this frame
            while True:
                elapsed = time.perf_counter() - playback_start
                if elapsed >= adjusted_t:
                    break
                remaining = adjusted_t - elapsed
                await asyncio.sleep(min(remaining, 0.001))

            # Adapt position count for current protocol
            pos = list(positions)
            pos = pos[:21]

            # Send positions
            await client.v3_set_all_motor_positions(slave_id, pos)
            frame_idx = i

            # Print progress every 2 seconds
            now = time.perf_counter()
            if now - last_print_time >= 2.0:
                actual_elapsed = now - playback_start
                progress = (i + 1) / trajectory.frame_count * 100
                pos_preview = " ".join([f"{positions[j]:6.1f}" for j in range(5)])
                logger.info(f"  [{actual_elapsed:.1f}s] {progress:.0f}% (frame {i+1}/{trajectory.frame_count}) "
                           f"| M0-4: {pos_preview}")
                last_print_time = now

    except asyncio.CancelledError:
        logger.info(f"Playback interrupted at frame {frame_idx}/{trajectory.frame_count}")
        return

    actual_duration = time.perf_counter() - playback_start
    logger.info(f"✅ Playback complete: {trajectory.frame_count} frames in {actual_duration:.2f}s "
               f"(target: {trajectory.duration / speed:.2f}s)")


# =============================================================================
# Interactive Control
# =============================================================================

async def wait_for_enter(prompt="Press Enter to continue..."):
    """Wait for Enter key press in a non-blocking way."""
    loop = asyncio.get_event_loop()
    print(f"\n  >>> {prompt}", end=" ", flush=True)
    await loop.run_in_executor(None, sys.stdin.readline)


async def wait_for_key_or_enter(prompt="Press Enter to stop recording..."):
    """Wait for Enter key press (runs in thread to not block event loop)."""
    loop = asyncio.get_event_loop()
    print(f"\n  >>> {prompt}", end=" ", flush=True)
    await loop.run_in_executor(None, sys.stdin.readline)


async def interactive_session(client, slave_id, motor_buffer, collector,
                              record_freq, save_path, load_path,
                              playback_speed, loop_count):
    """Run interactive teaching session."""

    trajectory = None

    # If loading from file, skip recording
    if load_path:
        trajectory = Trajectory.load(load_path)
        trajectory.summary()
    else:
        # === Phase 1: Record initial positions ===
        logger.info("=" * 60)
        logger.info("Phase 1: Save Initial State")
        logger.info("=" * 60)

        status = await client.v3_get_motor_status_data(slave_id)
        initial_positions = list(status.positions)
        logger.info(f"Initial positions (first 5): {[f'{p:.1f}' for p in initial_positions[:5]]}")

        # === Phase 2: Enter teaching mode ===
        logger.info("")
        logger.info("=" * 60)
        logger.info("Phase 2: Teaching Mode (Recording)")
        logger.info("=" * 60)
        await wait_for_enter("Press Enter to enter teaching mode (hand becomes compliant)...")

        await enter_teaching_mode(client, slave_id)
        await asyncio.sleep(0.3)  # Let motors settle

        # Use a shared dict to hold trajectory data, so it survives task cancellation
        result_holder = {}

        # Start recording in background
        record_task = asyncio.create_task(
            record_trajectory(client, slave_id, motor_buffer, record_freq, result_holder)
        )

        # Wait for user to press Enter to stop
        await wait_for_key_or_enter("Press Enter to stop recording...")

        # Stop recording
        record_task.cancel()
        try:
            await record_task
        except asyncio.CancelledError:
            pass

        # Retrieve trajectory from shared holder (always available regardless of cancellation)
        trajectory = result_holder.get('trajectory', Trajectory())

        # === Phase 3: Exit teaching mode ===
        logger.info("")
        logger.info("=" * 60)
        logger.info("Phase 3: Restore Control")
        logger.info("=" * 60)

        await exit_teaching_mode(client, slave_id, restore_positions=initial_positions)

        # Show trajectory summary
        logger.info("")
        logger.info("Recorded trajectory:")
        trajectory.summary()

        # Save if requested
        if save_path:
            trajectory.save(save_path)
        elif trajectory.frame_count > 0:
            # Auto-save with timestamp
            auto_path = f"trajectory_{int(time.time())}.json"
            trajectory.save(auto_path)

    # === Phase 4: Playback ===
    if trajectory and trajectory.frame_count >= 2:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Phase 4: Playback")
        logger.info("=" * 60)

        for loop_i in range(loop_count):
            if loop_count > 1:
                logger.info(f"\n--- Loop {loop_i + 1}/{loop_count} ---")

            # Stop DataCollector before prompting, to avoid warning spam
            # while waiting for user input and to free the serial bus for playback.
            if collector:
                collector.stop()
                collector.wait()
                logger.info("DataCollector paused for playback")

            await wait_for_enter(f"Press Enter to start playback ({playback_speed:.1f}x speed)...")

            await playback_trajectory(client, slave_id, trajectory,
                                     speed=playback_speed, motor_buffer=motor_buffer)

            # Restart DataCollector after playback (needed if recording follows)
            if collector:
                collector.start()
                await asyncio.sleep(0.2)

            # Return to initial position after playback
            if not load_path:
                await client.v3_set_all_motor_positions(slave_id, initial_positions)
            else:
                # If loaded from file, go to first frame position
                first_pos = trajectory.frames[0][1]
                await client.v3_set_all_motor_positions(slave_id, first_pos)
            await asyncio.sleep(0.5)

    logger.info("\n✅ Teaching session complete!")


# =============================================================================
# Main
# =============================================================================

async def main(port_name=None, record_freq=DEFAULT_RECORD_FREQ,
               save_path=None, load_path=None,
               playback_speed=DEFAULT_PLAYBACK_SPEED,
               loop_count=DEFAULT_LOOP_COUNT,
               ):
    """Main entry point."""

    # Set protocol version

    collector = None
    client = None

    try:
        # Connect to Revo3
        if port_name:
            client = await modbus_open(port_name, 5000000)
            slave_id = 1
        else:
            (protocol, detected_port, detected_baud, detected_slave) = (
                await libstark.auto_detect_modbus_revo3(None)
            )
            client = await modbus_open(detected_port, detected_baud)
            slave_id = detected_slave
            logger.info(f"Auto-detected: port={detected_port}, baudrate={detected_baud}, slave_id={slave_id}")

        # Create DataCollector for high-frequency position monitoring
        is_linux = platform.system() == "Linux"
        collector_freq = COLLECTOR_FREQ_LINUX if is_linux else COLLECTOR_FREQ

        motor_buffer = libstark.V3MotorStatusBuffer(max_size=2000)
        collector = libstark.DataCollector.new_v3_basic(
            ctx=client,
            motor_buffer=motor_buffer,
            slave_id=slave_id,
            motor_frequency=collector_freq,
            enable_stats=True,
        )
        collector.start()
        await asyncio.sleep(0.5)

        # Verify data collection
        test_data = motor_buffer.peek_latest()
        if test_data:
            pos_preview = " ".join([f"{test_data.positions[i]:.1f}" for i in range(5)])
            logger.info(f"✓ DataCollector running ({collector_freq}Hz), M0-4: {pos_preview}")
        else:
            logger.warning("DataCollector started but no data yet")

        # Run interactive session
        await interactive_session(
            client, slave_id, motor_buffer, collector,
            record_freq=record_freq,
            save_path=save_path,
            load_path=load_path,
            playback_speed=playback_speed,
            loop_count=loop_count,
        )

    except KeyboardInterrupt:
        logger.info("User interrupted (Ctrl+C)")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if collector:
            try:
                collector.stop()
                collector.wait()
            except Exception:
                pass
        if client:
            try:
                target = [0.0] * REVO3_MOTOR_COUNT
                await client.v3_set_all_motor_positions(slave_id, target)
            except Exception:
                pass
            try:
                libstark.modbus_close(client)
            except Exception:
                pass
        logger.info("Done. Closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Revo3 Teaching Mode - Record and Playback Hand Movements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive record and playback
  python revo3_teaching.py

  # Record at 50Hz, save to file
  python revo3_teaching.py --freq 50 --save my_trajectory.json

  # Load and playback at half speed, 3 loops
  python revo3_teaching.py --load my_trajectory.json --speed 0.5 --loop 3

  # Pen-spinning demo: record, save, then replay fast
  python revo3_teaching.py --save pen_spin.json
  python revo3_teaching.py --load pen_spin.json --speed 1.5 --loop 5
""")
    parser.add_argument("--port", "-p", type=str, default=None,
                        help="Serial port name (auto-detect if not specified)")
    parser.add_argument("--freq", "-f", type=int, default=DEFAULT_RECORD_FREQ,
                        help=f"Recording frequency in Hz (default: {DEFAULT_RECORD_FREQ})")
    parser.add_argument("--save", "-s", type=str, default=None,
                        help="Save trajectory to JSON file")
    parser.add_argument("--load", "-l", type=str, default=None,
                        help="Load trajectory from JSON file (skip recording)")
    parser.add_argument("--speed", type=float, default=DEFAULT_PLAYBACK_SPEED,
                        help=f"Playback speed multiplier (default: {DEFAULT_PLAYBACK_SPEED})")
    parser.add_argument("--loop", type=int, default=DEFAULT_LOOP_COUNT,
                        help=f"Number of playback loops (default: {DEFAULT_LOOP_COUNT})")
    args = parser.parse_args()

    try:
        asyncio.run(main(
            port_name=args.port,
            record_freq=args.freq,
            save_path=args.save,
            load_path=args.load,
            playback_speed=args.speed,
            loop_count=args.loop,

        ))
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
