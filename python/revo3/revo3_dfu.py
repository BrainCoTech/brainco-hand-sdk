"""
Revo3 Dexterous Hand Firmware Upgrade (DFU) Example

This example demonstrates how to perform a firmware upgrade for the Revo3 dexterous hand, including:
- Automatic device type and protocol detection
- Firmware file validation and path configuration
- Executing the firmware upgrade process and monitoring progress
- Handling upgrade status and result feedback

Important Warnings:
- Different hardware versions must use their corresponding firmware files
- Using the wrong firmware may cause the device to fail to start and require disassembly and reflashing
- Do not disconnect the device during the upgrade process
- Revo3 uses Modbus RTU register-based OTA (registers 500-573)
"""

import asyncio
import sys
import pathlib
import os
import time

from revo3_utils import *

# Firmware upgrade file path configuration
current_dir = pathlib.Path(__file__).resolve()
parent_dir = current_dir.parent.parent
logger.info(f"parent_dir: {parent_dir}")

# Revo3 dexterous hand firmware path
revo3_ota_bin_path = os.path.join(
    parent_dir,
    "ota_bin",
    "stark3",
    "placeholder.bin",  # Replace with actual firmware file
)

# Global variables for asynchronous event handling
shutdown_event = None
main_loop = None


def on_dfu_state(_slave_id, state):
    """
    DFU state change callback function

    Called when the state changes during the firmware upgrade process.

    Args:
        _slave_id: Device ID (not used)
        state: DFU state enumeration value
    """
    logger.info(f"DFU STATE: {libstark.DfuState(state)}")
    dfu_state = libstark.DfuState(state)

    # When the upgrade is completed or aborted, set the shutdown event
    if (
        dfu_state == libstark.DfuState.Completed
        or dfu_state == libstark.DfuState.Aborted
    ):
        if main_loop and shutdown_event:
            if not shutdown_event.is_set():
                logger.info("Using call_soon_threadsafe to set event")
                main_loop.call_soon_threadsafe(shutdown_event.set)


def on_dfu_progress(_slave_id, progress):
    """
    DFU progress update callback function

    Called periodically during the firmware upgrade process to report progress.

    Args:
        _slave_id: Device ID (not used)
        progress: Upgrade progress, range 0.0-1.0
    """
    if progress >= 1.0:
        print(f"\r[DFU] progress: 100%")
    else:
        print(f"[DFU] progress: {progress * 100.0:.1f}%\r", end="", flush=True)


async def main():
    """
    Main function: execute the firmware upgrade process
    """
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Check for firmware file argument
    ota_bin_path = revo3_ota_bin_path
    if len(sys.argv) > 1:
        ota_bin_path = sys.argv[1]
        logger.info(f"Using firmware file from argument: {ota_bin_path}")

    # Verify that the firmware file exists
    if not os.path.exists(ota_bin_path):
        logger.warning(f"OTA file does not exist: {ota_bin_path}")
        logger.info("Usage: python revo3_dfu.py [firmware_file_path]")
        exit(1)
    else:
        logger.info(f"OTA file path: {ota_bin_path}")
        file_size = os.path.getsize(ota_bin_path)
        logger.info(f"OTA file size: {file_size} bytes")

    # Automatically detect device connection
    (client, slave_id) = await open_modbus_revo3()

    # Execute firmware upgrade
    await start_dfu(client, slave_id, ota_bin_path)

    sys.exit(0)


async def start_dfu(client, slave_id, ota_bin_path):
    """
    Start the firmware upgrade process

    Args:
        client: Modbus client instance
        slave_id: Device slave ID
        ota_bin_path: Firmware file path
    """
    global shutdown_event
    shutdown_event = asyncio.Event()

    # Get device information
    try:
        device_info = await client.get_device_info(slave_id)
        logger.info(f"Device info: {device_info.description}")
    except Exception as e:
        logger.warning(f"Could not get device info: {e}")

    start_time = time.perf_counter()

    # Start firmware upgrade
    # Revo3 OTA is handled internally by the SDK using Modbus RTU registers 500-573
    # No need to specify wait_seconds as the protocol uses synchronous FC16 confirmation
    wait_seconds = 5  # Wait for device to initialize OTA mode
    await client.start_dfu(
        slave_id,
        ota_bin_path,
        wait_seconds,
        on_dfu_state,      # State change callback
        on_dfu_progress,    # Progress update callback
    )

    # Wait for upgrade to complete
    logger.info("Revo3 Modbus DFU, Waiting for DFU to complete...")
    await shutdown_event.wait()
    logger.info("DFU completed, shutdown event received!")
    elapsed = time.perf_counter() - start_time
    logger.info(f"Elapsed: {elapsed:.1f}s")

    # Clean up resources
    libstark.modbus_close(client)
    logger.info("Modbus client closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
