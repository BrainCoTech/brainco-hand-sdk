"""
Armband Serial DFU Example

Usage:
    python armband_serial_dfu.py path/to/firmware.ota
"""

import asyncio
import sys

from edu_utils import get_armband_port_name, libedu, logger


def on_progress(progress):
    logger.info(
        "DFU %s: %.1f%% (%d/%d bytes) %s",
        progress.state,
        progress.percentage,
        progress.uploaded_bytes,
        progress.total_bytes,
        progress.message,
    )


async def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python armband_serial_dfu.py path/to/firmware.ota")

    firmware_path = sys.argv[1]
    port_name = get_armband_port_name()
    if not port_name:
        raise RuntimeError("No armband serial port found")

    await libedu.perform_serial_dfu_py(
        port_name,
        firmware_path,
        on_progress=on_progress,
        chunk_size=512,
        via_mcu=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
