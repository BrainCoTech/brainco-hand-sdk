"""
Revo3 Modbus I/O Benchmark (No GUI, No Logging, Pure I/O Loop)

This script acts as the ultimate physical link testing tool, supporting ultra-high-speed 
unidirectional and bidirectional read/write benchmarks.

Modes:
  --mode write        : Only send MIT sine wave control commands (no reads).
  --mode read         : Only poll motor positions in a tight loop (no writes).
  --mode both         : [Default] Alternates reading positions and writing MIT control.
  --mode write-heavy  : Send MIT commands full-speed, fetch positions once per second.
  --mode read-heavy   : Fetch positions full-speed, send one MIT command once per second.

Usage:
  python revo3/revo3_benchmark.py
  python revo3/revo3_benchmark.py --mode write
  python revo3/revo3_benchmark.py --mode read-heavy --port /dev/ttyUSB0
"""

import sys
import os
import time
import math
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import modbus_open
from revo3.revo3_utils import libstark, logger

async def main(port=None, mode="both"):
    logger.info("Auto-detecting Revo3 on Modbus...")
    try:
        if port:
            client = await modbus_open(port, 5000000)
            slave_id = 1
        else:
            (protocol, detected_port, baud, slave_id) = await libstark.auto_detect_modbus_revo3(None)
            logger.info(f"Detected Revo3 on port={detected_port}, slave_id={slave_id}")
            client = await modbus_open(detected_port, baud)
    except Exception as e:
        logger.error(f"Connection failed. Check USB serial or hand power. Error: {e}")
        return

    # Disable constraints & motors holding to be safe
    logger.info("Pre-flight: Releasing M3 to safe idle state...")
    try:
        await client.revo3_mit_control(slave_id, 3, 0.0, 0.0, 0.0, 0.0, 0.0)
    except:
        pass

    logger.info("="*50)
    logger.info(f"🚀 Starting Pure I/O Benchmark | Mode: {mode.upper()}")
    if mode in ("write", "both", "write-heavy"):
        logger.info("  -> Primary/Always: Send MIT Sine wave to M3")
    if mode in ("read", "both", "read-heavy"):
        logger.info("  -> Primary/Always: Read 21 joint positions")
    if mode in ("write-heavy", "read-heavy"):
        logger.info("  -> Rare injection: Executing opposite command once per 1.0 second")
    logger.info("Press Ctrl+C to abort...")
    logger.info("="*50)

    total_loops = 0
    start_time = time.perf_counter()
    last_print = start_time
    last_rare_op = start_time
    loops_since_print = 0
    pos_str = "N/A"

    # Start moving loop smoothly
    sine_freq = 0.5  # 0.5 Hz sine wave
    amplitude = 40.0 # Swing between 0 and 80 degrees

    try:
        # TIGHT LOOP: Absolutely nothing but serial transactions
        while True:
            now = time.perf_counter()
            do_write = False
            do_read = False

            # Determine operations for this specific loop tick
            if mode == "both":
                do_write = True
                do_read = True
            elif mode == "write":
                do_write = True
            elif mode == "read":
                do_read = True
            elif mode == "write-heavy":
                do_write = True
                if now - last_rare_op >= 1.0:
                    do_read = True
                    last_rare_op = now
            elif mode == "read-heavy":
                do_read = True
                if now - last_rare_op >= 1.0:
                    do_write = True
                    last_rare_op = now

            if do_write:
                # Calculate sine wave dynamically
                phase = 2 * math.pi * sine_freq * now
                sine_pos = amplitude - amplitude * math.cos(phase)
                sine_vel_rpm = (amplitude * 2 * math.pi * sine_freq * math.sin(phase)) / 6.0
                
                # 1. WRITE: Send MIT command to M03
                await client.revo3_mit_control(slave_id, 3, 5.0, 0.5, sine_pos, sine_vel_rpm, 0.0)

            if do_read:
                # 2. READ: Request all position data
                positions = await client.v3_get_all_motor_positions(slave_id)
                pos_str = f"{positions[3]:.1f}°"

            total_loops += 1
            loops_since_print += 1

            # 3. Rate printing calculation
            elapsed_sec = now - last_print
            if elapsed_sec >= 1.0:
                hz = loops_since_print / elapsed_sec
                logger.info(f"⚡ Real-time {mode.upper()} Rate: {hz:.1f} Hz (M3 pos: {pos_str})")
                
                # Reset counters
                last_print = now
                loops_since_print = 0

    except KeyboardInterrupt:
        logger.info("\nCaught KeyboardInterrupt, wrapping up...")
    except Exception as e:
        logger.error(f"Runtime error during I/O loop: {e}")
    finally:
        # Halt motor safely
        try:
            await client.revo3_mit_control(slave_id, 3, 0.0, 0.0, 0.0, 0.0, 0.0)
        except:
            pass

        total_time = time.perf_counter() - start_time
        overall_hz = total_loops / total_time if total_time > 0 else 0
        logger.info("="*50)
        logger.info(f"🏁 Benchmark Finished: {total_time:.2f}s")
        logger.info(f"Total Loops executed: {total_loops}")
        logger.info(f"Overall Average Freq: {overall_hz:.1f} Hz")
        logger.info("="*50)
        libstark.modbus_close(client)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=str, default=None, help="Force serial port")
    parser.add_argument("--mode", type=str, choices=["write", "read", "both", "write-heavy", "read-heavy"], default="both", 
                        help="Testing ratio mode")
    args = parser.parse_args()
    
    asyncio.run(main(args.port, args.mode))
