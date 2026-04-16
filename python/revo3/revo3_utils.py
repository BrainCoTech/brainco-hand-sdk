"""
Revo3 Dexterous Hand Utility Functions Module

This module provides common utility functions for Revo3 (21 DoF) dexterous hand, including:
- Automatic detection and establishment of Modbus connection
- Device information retrieval and verification
"""

import sys
import os

# Import from common_imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import logger, libstark, int_to_baudrate, modbus_open

libstark.init_logging()

__all__ = [
    'logger', 'libstark', 'int_to_baudrate', 'modbus_open',
    'open_modbus_revo3',
    'REVO3_MOTOR_COUNT', 'REVO3_FINGER_COUNT', 'FINGER_NAMES',
]

REVO3_MOTOR_COUNT = 21
REVO3_FINGER_COUNT = 5
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


async def open_modbus_revo3(port_name=None, baudrate=5000000, slave_id=1):
    """
    Open Modbus connection for Revo3 dexterous hand

    Revo3 uses 5Mbps baudrate by default.

    Args:
        port_name (str, optional): Serial port name, None means auto-detect.
        baudrate (int, optional): Baud rate, default 5000000 (5Mbps).
        slave_id (int, optional): Device slave ID, default 1.

    Returns:
        tuple: (client, slave_id) - Modbus client instance and device slave ID
    """
    try:
        if port_name is None:
            # Auto-detect
            (protocol, detected_port_name, detected_baudrate, detected_slave_id) = (
                await libstark.auto_detect_modbus_revo3(port_name)
            )
            port_name = detected_port_name
            baudrate = detected_baudrate
            slave_id = detected_slave_id
            logger.info(f"Auto-detected: port={port_name}, baudrate={baudrate}, slave_id={slave_id}")
    except Exception as e:
        logger.error(f"Auto-detect failed: {e}")
        if port_name is None:
            sys.exit(1)

    # Establish Modbus connection
    client: libstark.DeviceContext = await modbus_open(port_name, baudrate)

    return (client, slave_id)
