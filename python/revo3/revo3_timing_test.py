"""
Revo3 Single Motor Timing Test (No GUI)

Tests a single motor (default: M3) open/close timing performance.
Uses DataCollector for high-frequency position monitoring.

Usage:
    python revo3_timing_test.py                  # Test M3 (default)
    python revo3_timing_test.py --motor 5        # Test M5
    python revo3_timing_test.py --motor 3 --cycles 10
    python revo3_timing_test.py --motor 3 --angle 60.0
    python revo3_timing_test.py --port /dev/ttyUSB0
"""

import asyncio
import sys
import os
import time
import platform
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import modbus_open
from revo3.revo3_utils import *

# Test configuration
DEFAULT_MOTOR_ID = 3
DEFAULT_NUM_CYCLES = 5
DEFAULT_TIMEOUT = 2.0        # Max seconds per movement
DEFAULT_CLOSE_ANGLE = 90.0   # Target close angle (degrees)
OPEN_ANGLE = 0.0             # Open position (degrees)
THRESHOLD_RATIO = 0.90       # 90% of target = reached
POLL_INTERVAL = 0.001        # 1ms polling (matches ~1000Hz reading)


async def measure_movement(motor_buffer, motor_id, target_angle, timeout):
    """Measure time for a single motor to reach target position.

    Returns:
        tuple: (elapsed_time, final_position, reached, read_count)
    """
    start_time = time.perf_counter()
    read_count = 0

    while True:
        elapsed = time.perf_counter() - start_time

        latest = motor_buffer.peek_latest()
        if latest and hasattr(latest, 'positions'):
            read_count += 1
            current = latest.positions[motor_id]

            # Check if target reached
            if abs(target_angle) < 1.0:
                # Opening: accept within 5° of target
                reached = abs(current - target_angle) <= 5.0
            else:
                # Closing: accept within 90% of target
                reached = abs(current) >= abs(target_angle) * THRESHOLD_RATIO

            if reached:
                return (elapsed, current, True, read_count)

        if elapsed >= timeout:
            pos = latest.positions[motor_id] if latest else float('nan')
            return (elapsed, pos, False, read_count)

        await asyncio.sleep(POLL_INTERVAL)


async def run_timing_test(client, slave_id, motor_buffer, motor_id, num_cycles, close_angle, timeout, motor_freq):
    """Run timing test for a single motor."""
    logger.info(f"{'='*60}")
    logger.info(f"Revo3 Single Motor Timing Test")
    logger.info(f"  Motor: M{motor_id}")
    logger.info(f"  Cycles: {num_cycles}")
    logger.info(f"  Close angle: {close_angle}°")
    logger.info(f"  Timeout: {timeout}s")
    logger.info(f"  DataCollector: {motor_freq}Hz ({platform.system()})")
    logger.info(f"  Poll interval: {POLL_INTERVAL*1000:.0f}ms")
    logger.info(f"{'='*60}")

    # Prepare positions: all open, only target motor moves
    open_positions = [OPEN_ANGLE] * REVO3_MOTOR_COUNT
    close_positions = [OPEN_ANGLE] * REVO3_MOTOR_COUNT
    close_positions[motor_id] = close_angle

    # Move to initial position
    logger.info("Moving to initial position (all open)...")
    await client.v3_set_all_motor_positions(slave_id, open_positions)
    await asyncio.sleep(2.0)

    close_times = []
    open_times = []
    total_reads = 0
    test_start = time.perf_counter()

    for cycle in range(num_cycles):
        logger.info(f"\n--- Cycle {cycle + 1}/{num_cycles} ---")

        # === CLOSE ===
        logger.info(f"  CLOSE: M{motor_id} 0° → {close_angle}°")
        motor_buffer.clear()
        await client.v3_set_all_motor_positions(slave_id, close_positions)

        elapsed, pos, reached, reads = await measure_movement(
            motor_buffer, motor_id, close_angle, timeout
        )
        close_times.append(elapsed)
        total_reads += reads
        freq = reads / elapsed if elapsed > 0.001 else 0
        status = "✓" if reached else "⚠ TIMEOUT"
        logger.info(f"  {status} Close: {elapsed:.3f}s (pos={pos:.1f}°, reads={reads}, freq={freq:.0f}Hz)")

        # === OPEN ===
        logger.info(f"  OPEN:  M{motor_id} {close_angle}° → 0°")
        motor_buffer.clear()
        await client.v3_set_all_motor_positions(slave_id, open_positions)

        elapsed, pos, reached, reads = await measure_movement(
            motor_buffer, motor_id, OPEN_ANGLE, timeout
        )
        open_times.append(elapsed)
        total_reads += reads
        freq = reads / elapsed if elapsed > 0.001 else 0
        status = "✓" if reached else "⚠ TIMEOUT"
        logger.info(f"  {status} Open:  {elapsed:.3f}s (pos={pos:.1f}°, reads={reads}, freq={freq:.0f}Hz)")

    test_duration = time.perf_counter() - test_start

    # === Summary ===
    print_summary(motor_id, close_angle, close_times, open_times,
                  total_reads, test_duration, motor_freq)


def print_summary(motor_id, close_angle, close_times, open_times,
                  total_reads, test_duration, motor_freq):
    """Print test summary statistics."""
    logger.info(f"\n{'='*60}")
    logger.info(f"M{motor_id} Timing Test Results ({len(close_times)} cycles)")
    logger.info(f"{'='*60}")

    # Communication stats
    actual_freq = total_reads / test_duration if test_duration > 0 else 0
    avg_latency_ms = (test_duration / total_reads * 1000) if total_reads > 0 else 0
    logger.info(f"📊 Communication Statistics:")
    logger.info(f"  Target frequency:  {motor_freq} Hz")
    logger.info(f"  Actual read freq:  {actual_freq:.1f} Hz")
    logger.info(f"  Avg read latency:  {avg_latency_ms:.1f} ms")
    logger.info(f"  Total reads:       {total_reads}")
    logger.info(f"  Test duration:     {test_duration:.1f}s")
    logger.info(f"  Platform:          {platform.system()}")

    logger.info(f"")
    if close_times:
        avg_close = sum(close_times) / len(close_times)
        logger.info(f"⏱ CLOSE (0° → {close_angle}°):")
        logger.info(f"  Average: {avg_close:.3f}s")
        logger.info(f"  Min: {min(close_times):.3f}s, Max: {max(close_times):.3f}s")
        logger.info(f"  All: {', '.join(f'{t:.3f}s' for t in close_times)}")

    if open_times:
        avg_open = sum(open_times) / len(open_times)
        logger.info(f"⏱ OPEN ({close_angle}° → 0°):")
        logger.info(f"  Average: {avg_open:.3f}s")
        logger.info(f"  Min: {min(open_times):.3f}s, Max: {max(open_times):.3f}s")
        logger.info(f"  All: {', '.join(f'{t:.3f}s' for t in open_times)}")

    if close_times and open_times:
        avg_round = (sum(close_times) + sum(open_times)) / len(close_times)
        logger.info(f"⏱ ROUND TRIP (close + open):")
        logger.info(f"  Average: {avg_round:.3f}s")
        logger.info(f"  Max throughput: {1.0/avg_round:.1f} cycles/s")

    logger.info(f"{'='*60}")


async def main(port_name=None, motor_id=DEFAULT_MOTOR_ID, num_cycles=DEFAULT_NUM_CYCLES,
               close_angle=DEFAULT_CLOSE_ANGLE, timeout=DEFAULT_TIMEOUT, ):
    """Main function."""
    # Set protocol version before connecting

    collector = None
    client = None

    try:
        # Connect to Revo3 (bypass get_device_info which may fail if SN is empty)
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

        # Validate motor_id
        if motor_id < 0 or motor_id >= REVO3_MOTOR_COUNT:
            logger.error(f"Invalid motor_id: {motor_id} (must be 0-{REVO3_MOTOR_COUNT - 1})")
            return

        # Create DataCollector
        is_linux = platform.system() == "Linux"
        motor_freq = 2000 if is_linux else 200
        logger.info(f"DataCollector motor_frequency={motor_freq}Hz ({platform.system()})")

        motor_buffer = libstark.V3MotorStatusBuffer(max_size=1000)
        collector = libstark.DataCollector.new_v3_basic(
            ctx=client,
            motor_buffer=motor_buffer,
            slave_id=slave_id,
            motor_frequency=motor_freq,
            enable_stats=True,
        )
        collector.start()
        await asyncio.sleep(0.5)

        # Verify collector is working
        test_data = motor_buffer.peek_latest()
        if test_data:
            logger.info(f"✓ DataCollector running, M{motor_id} pos={test_data.positions[motor_id]:.1f}°")
        else:
            logger.warning("DataCollector started but no data yet, continuing...")

        # Run timing test
        await run_timing_test(client, slave_id, motor_buffer, motor_id, num_cycles, close_angle, timeout, motor_freq)

    except KeyboardInterrupt:
        logger.info("User interrupted")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if collector:
            collector.stop()
            collector.wait()
        if client:
            libstark.modbus_close(client)
        logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Single Motor Timing Test (No GUI)")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port name (auto-detect if not specified)")
    parser.add_argument("--motor", "-m", type=int, default=DEFAULT_MOTOR_ID, help=f"Motor ID to test (0-22, default: {DEFAULT_MOTOR_ID})")
    parser.add_argument("--cycles", "-c", type=int, default=DEFAULT_NUM_CYCLES, help=f"Number of open/close cycles (default: {DEFAULT_NUM_CYCLES})")
    parser.add_argument("--angle", "-a", type=float, default=DEFAULT_CLOSE_ANGLE, help=f"Close angle in degrees (default: {DEFAULT_CLOSE_ANGLE})")
    parser.add_argument("--timeout", "-t", type=float, default=DEFAULT_TIMEOUT, help=f"Timeout per movement in seconds (default: {DEFAULT_TIMEOUT})")
    args = parser.parse_args()

    try:
        asyncio.run(main(
            port_name=args.port,
            motor_id=args.motor,
            num_cycles=args.cycles,
            close_angle=args.angle,
            timeout=args.timeout,
            
        ))
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
