"""
Armband EMG & Quaternion Data Collection Example

This example demonstrates how to connect to the armband device and collect EMG (electromyography) data,
while also leveraging the SDK's native high-performance 9-axis MARG attitude fusion to obtain
stabilized Quaternions and Euler angles directly from the Rust drivers.
"""

import asyncio
import numpy as np
from filters_sdk import *
from model import EMGData
from edu_utils import *

# Configuration constants
SAMPLING_FREQUENCY = 250  # EMG sampling frequency (Hz)
NUM_CHANNELS = 8  # Number of EMG channels
EMG_BUFFER_LENGTH = 1250  # EMG data buffer length (number of data points)
BAUDRATE = 115200  # Serial port baudrate
DATA_PRINT_INTERVAL = 0.2  # Print interval (seconds)

# Global variables
emg_values = np.zeros((NUM_CHANNELS, EMG_BUFFER_LENGTH))  # EMG sensor data buffer


def update_emg_buffer(emg_data: EMGData) -> None:
    """
    Update the EMG sensor data buffer

    Args:
        emg_data: EMG data object
    """
    channel_values = np.array_split(emg_data.channel_values, NUM_CHANNELS)
    for i in range(NUM_CHANNELS):
        emg_values[i] = np.roll(emg_values[i], -1)  # Roll the data to the left
        raw_value = channel_values[i][0]
        emg_values[i, -1] = raw_value  # Append the latest data point


def on_emg_data(data: list[list[float]]) -> None:
    """
    Process EMG packets from the SDK callback.
    """
    if not data:
        return

    emg_data_list = []
    for row in data:
        emg_data = EMGData.from_data(row)
        emg_data_list.append(emg_data)
        update_emg_buffer(emg_data)

    print_emg_timestamps(logger, emg_data_list)


def on_quaternion_data(data: list[list[float]]) -> None:
    """
    Print the latest native SDK quaternion from the callback.
    """
    if not data:
        return

    latest = data[-1]
    seq, w, x, y, z = int(latest[0]), latest[1], latest[2], latest[3], latest[4]
    logger.info(
        f"-> 📦 [SDK Quat Callback] Seq: {seq:5d} | "
        f"w={w:+.4f}, x={x:+.4f}, y={y:+.4f}, z={z:+.4f}"
    )


async def setup_armband_device():
    """
    Setup and connect the armband device

    Returns:
        EduDevice: Returns the device instance if connection succeeds, None otherwise
    """
    # Get the armband device port (auto-detect or manually specify)
    libedu.get_usb_available_ports()
    port_name = get_armband_port_name()

    if port_name is None:
        logger.error("No armband device found")
        return None

    try:
        device = libedu.EduDevice(port_name, BAUDRATE)
        parser = libedu.MessageParser("ARMBAND-device", libedu.MsgType.Edu)

        # Create recommended SensorProfile config
        profile = libedu.SensorProfile(
            flex_rate=None,
            imu_rate=libedu.ImuSampleRate.IMU_SR_100,
            imu_data_type=libedu.UploadDataType.CALIBRATED_DATA,
            emg_rate=libedu.AfeSampleRate.AFE_SR_250,
            emg_channel_bits=0xFF,
            mag_rate=libedu.MagSampleRate.MAG_SR_100,
            mag_data_type=libedu.UploadDataType.CALIBRATED_DATA
        )

        # One-key lifecycle: open serial parser, apply sensor configs, then send START_DATA_STREAM.
        await device.start_stream(parser, profile)
        logger.info("Serial stream opened, sensor config applied, and firmware data stream started via start_stream API")

        # Query device information and pairing status optionally
        await device.get_device_info()
        await asyncio.sleep(0.1)
        await device.get_dongle_pair_stat()
        await asyncio.sleep(0.1)

        return device

    except Exception as e:
        logger.error(f"Failed to setup armband device: {e}")
        return None


def initialize_configuration() -> None:
    """
    Initialize the SDK configuration and register callbacks
    """
    logger.info("Initializing SDK configurations...")
    libedu.set_emg_buffer_cfg(EMG_BUFFER_LENGTH)
    libedu.set_msg_resp_callback(
        lambda device_id, msg: logger.warning(f"Message response from {device_id}: {msg}")
    )

    # 1. Configure dynamic fusion mode in the Rust driver
    # Choose between: FusionMode.Imu6Axis or FusionMode.Marg9Axis (Earth-relative)
    libedu.set_fusion_mode(libedu.FusionMode.Imu6Axis)

    libedu.set_emg_data_callback(on_emg_data)
    libedu.set_quaternion_data_callback(on_quaternion_data)

    # 3. Register native Euler Angle data callback (Optional, for backwards compatibility)
    def euler_callback(data):
        if not data:
            return
        latest = data[-1]
        seq, yaw, pitch, roll = int(latest[0]), latest[1], latest[2], latest[3]
        print(
            f"⚡ [Euler Callback] Seq: {seq:5d} | "
            f"Yaw: {yaw:6.1f}° | Pitch: {pitch:6.1f}° | Roll: {roll:6.1f}°"
        )

    libedu.set_euler_data_callback(euler_callback)


async def main() -> None:
    """
    Main function: initialize configurations, connect the device, and start the EMG data collection loop
    """
    initialize_configuration()

    device = await setup_armband_device()
    if device is not None:
        logger.info("Armband device setup completed successfully")
    else:
        logger.error("Failed to setup armband device")
        return

    logger.info("Starting EMG data collection loop...")
    try:
        while True:
            await asyncio.sleep(DATA_PRINT_INTERVAL)
    except KeyboardInterrupt:
        logger.info("EMG data collection stopped by user")
    except Exception as e:
        logger.error(f"Error in data collection loop: {e}")
        raise e
    finally:
        logger.info("Stopping sensor data stream and releasing serial port...")
        try:
            await device.stop_stream()
        except Exception as e:
            logger.error(f"Error while stopping data stream: {e}")
        libedu.set_emg_data_callback(None)
        libedu.set_quaternion_data_callback(None)
        libedu.set_euler_data_callback(None)


if __name__ == "__main__":
    asyncio.run(main())
