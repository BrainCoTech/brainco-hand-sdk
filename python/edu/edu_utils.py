"""
Education SDK Utilities

This module provides helper utility functions for interacting with the bc-edu-sdk,
mainly used for device discovery, port management, and generic helper features.
"""

import json
import logging
from typing import Optional, List, Dict, Any

from logger import getLogger
from bc_edu_sdk import main_mod

# Configuration constants
VENDOR_ID = 21059  # BrainCo VID
GLOVE_PRODUCT_ID = 6  # Glove PID
ARMBAND_PRODUCT_ID_PRIMARY = 1  # Primary Armband PID
ARMBAND_PRODUCT_ID_SECONDARY = 5  # Secondary Armband PID

# Initialize logging and SDK module
# logger = getLogger(logging.DEBUG)  # Optional: use DEBUG log level
logger = getLogger(logging.INFO)   # Default: use INFO log level
libedu = main_mod

def get_usb_available_ports() -> None:
    """
    Get all available USB ports information

    This is a helper function to print all available USB ports currently in the system,
    mainly used for debugging and port discovery.
    """
    libedu.get_usb_available_ports()


def _get_first_port_name(ports_data: bytes, device_type: str) -> Optional[str]:
    """
    Helper function to extract the first available port name from port data

    This function parses port scan results of various devices and extracts the first
    available port name. It supports JSON format port data parsing with complete
    error handling and logging.

    Args:
        ports_data: Port data in JSON bytes
            Expected format: [{"port_name": "COM1", ...}, {"port_name": "COM2", ...}]
        device_type: Device type name, used for logging identification (e.g. "Stark", "Glove", "Armband")

    Returns:
        The name of the first available port, or None if parsing fails
        Returns the port name on success, e.g. "/dev/ttyUSB0", "COM3" etc.

    Note:
        - This function prefers to choose the first port in the list.
        - Contains complete error handling to ensure program stability.
        - All operations are logged to aid in debugging.
    """
    logger.info(f"Available {device_type} ports: {ports_data}")

    try:
        # Decode bytes object and parse JSON format data
        ports_json: List[Dict[str, Any]] = json.loads(ports_data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to parse {device_type} ports data: {e}")
        return None

    # Check if parsed results are empty
    if not ports_json:
        logger.warning(f"No {device_type} ports found in scan results")
        return None

    # Extract the first port name
    try:
        port_name = ports_json[0]["port_name"]
        logger.info(f"Using {device_type} port: {port_name}")
        return port_name
    except (KeyError, IndexError) as e:
        logger.error(f"Invalid port data structure for {device_type}: {e}")
        return None

def get_glove_port_name() -> Optional[str]:
    """
    Get the first available Glove device port name

    Scans for glove devices using USB VID/PID and returns the first detected port name.
    Uses specific VENDOR_ID and PRODUCT_ID to identify the glove.

    Returns:
        The first available port name, or None if not found or parsing fails
        Returns the port name on success, e.g. "/dev/ttyUSB0", "COM3" etc.

    Note:
        - Identifies the glove using VID=21059, PID=6.
        - This function is specifically for USB-connected gloves.
        - If there are multiple gloves, it only returns the first detected port.

    Example:
        >>> port = get_glove_port_name()
        >>> if port:
        ...     print(f"Found glove device at: {port}")
        ... else:
        ...     print("No glove device found")
    """
    try:
        ports = libedu.available_usb_ports(VENDOR_ID, GLOVE_PRODUCT_ID)
        return _get_first_port_name(ports, "Glove")
    except Exception as e:
        logger.error(f"Error scanning for glove devices: {e}")
        return None


def get_armband_port_name() -> Optional[str]:
    """
    Get the first available Armband device port name

    Scans for armband devices using USB VID/PID and returns the first detected port name.
    Supports multiple product IDs to increase device compatibility.

    Returns:
        The first available port name, or None if not found or parsing fails
        Returns the port name on success, e.g. "/dev/ttyUSB0", "COM3" etc.

    Note:
        - Tries the primary product ID (PID=1) first, then the secondary product ID (PID=5).
        - This function is specifically for USB-connected armbands.
        - If there are multiple armbands, it only returns the first detected port.

    Example:
        >>> port = get_armband_port_name()
        >>> if port:
        ...     print(f"Found armband device at: {port}")
        ... else:
        ...     print("No armband device found")
    """
    try:
        # Try primary product ID first
        ports = libedu.available_usb_ports(VENDOR_ID, ARMBAND_PRODUCT_ID_PRIMARY)
        port_name = _get_first_port_name(ports, "Armband")

        if port_name:
            return port_name

        # If primary product ID is not found, try secondary product ID
        logger.info("Primary armband product ID not found, trying secondary ID...")
        ports = libedu.available_usb_ports(VENDOR_ID, ARMBAND_PRODUCT_ID_SECONDARY)
        return _get_first_port_name(ports, "Armband")

    except Exception as e:
        logger.error(f"Error scanning for armband devices: {e}")
        return None


def get_all_device_ports() -> Dict[str, Optional[str]]:
    """
    Get all supported device port information

    Returns:
        A dictionary containing all device types and their corresponding ports
        Format: {"glove": "COM3", "armband": "/dev/ttyUSB0"}
    """
    devices = {
        "glove": get_glove_port_name(),
        "armband": get_armband_port_name()
    }

    logger.info(f"Device scan results: {devices}")
    return devices


def is_device_connected(device_type: str) -> bool:
    """
    Check if a device of a specified type is connected

    Args:
        device_type: Device type ("glove" or "armband")

    Returns:
        True if the device is connected, False otherwise
    """
    if device_type.lower() == "glove":
        return get_glove_port_name() is not None
    elif device_type.lower() == "armband":
        return get_armband_port_name() is not None
    else:
        logger.warning(f"Unknown device type: {device_type}")
        return False


def scan_and_report_devices() -> None:
    """
    Scan and report all connected devices

    This is a helper function to quickly review the status of all currently connected devices.
    """
    logger.info("Scanning for connected devices...")

    devices = get_all_device_ports()
    connected_devices = [name for name, port in devices.items() if port is not None]

    if connected_devices:
        logger.info(f"Found {len(connected_devices)} connected device(s):")
        for device_name, port in devices.items():
            if port:
                logger.info(f"  - {device_name.capitalize()}: {port}")
    else:
        logger.warning("No devices found. Please check connections.")

    # Display all available ports as reference
    logger.info("All available USB ports:")
    get_usb_available_ports()


def print_emg_timestamps(logger, data) -> None:
    """
    Elegant single-line printing of EMG data batch summary and core status to avoid verbose logs

    Args:
        logger: Logger instance
        data: EMG data list
    """
    if not data:
        return

    first_seq = data[0].seq_num
    last_seq = data[-1].seq_num
    latest = data[-1]

    bits = int(latest.lead_off_bits)
    if bits == 0:
        lead_off_str = "Normal"
    else:
        loose_channels = [f"CH{i+1}" for i in range(8) if (bits & (1 << i)) != 0]
        lead_off_str = f"Loose({', '.join(loose_channels)})"

    seq_range = f"{first_seq}" if first_seq == last_seq else f"{first_seq} ~ {last_seq}"
    logger.info(
        f"-> Received {len(data)} EMG packets (seq: {seq_range}) | "
        f"lead_off: {lead_off_str}"
    )
