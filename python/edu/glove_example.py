"""
Glove Data Collection Example

This example demonstrates how to connect to the glove device and collect sensor data,
including Flex (bending sensors), IMU (inertial measurement unit), and magnetometer data.
"""

import asyncio
import numpy as np
from typing import Optional, List

from edu_utils import *
from model import FlexData, IMUData, MagData

# Configuration constants
BAUDRATE = 115200  # Serial port baudrate
NUM_CHANNELS = 6  # Number of Flex sensor channels
FLEX_BUFFER_LENGTH = 1250  # Flex data buffer length (number of data points)

# Sensor coefficients
ACC_COEFFICIENT = 0.0001220703125  # Accelerometer coefficient (1/8192)
GYRO_COEFFICIENT = 0.06103515625  # Gyroscope coefficient (1/16.4)
MAG_COEFFICIENT = 0.00152587890625  # Magnetometer coefficient (1/65536)

# Global variables
flex_seq_num: Optional[int] = None  # Flex packet sequence number
flex_values = np.zeros((NUM_CHANNELS, FLEX_BUFFER_LENGTH))  # Flex sensor data buffer
imu_packet_count = 0
mag_packet_count = 0

def on_mag_data(data: List[List[float]]) -> None:
    """
    Callback function to handle incoming magnetometer data
    """
    global mag_packet_count
    logger.debug(f"Got mag callback len={len(data)}")

    if len(data) == 0:
        return

    mag_packet_count += len(data)
    if mag_packet_count % 30 < len(data):
        # Print only the first Mag data frame as an example
        mag_data = MagData.from_data(data[0])
        logger.info(f"📈 [MAG DATA] seq: {mag_data.seqnum}, Mag: [{mag_data.data.cord_x:.3f}, {mag_data.data.cord_y:.3f}, {mag_data.data.cord_z:.3f}] Gauss")


def on_imu_data(data: List[List[float]]) -> None:
    """
    Callback function to handle incoming IMU data
    """
    global imu_packet_count
    logger.debug(f"Got IMU callback len={len(data)}")

    if len(data) == 0:
        return

    imu_packet_count += len(data)
    if imu_packet_count % 30 < len(data):
        row = data[0]
        imu_data = IMUData.from_data(row)
        logger.info(
            f"📈 [IMU DATA] seq: {imu_data.seqnum}, Acc: [{imu_data.acc.cord_x:.3f}, {imu_data.acc.cord_y:.3f}, {imu_data.acc.cord_z:.3f}] g, "
            f"Gyro: [{imu_data.gyro.cord_x:.2f}, {imu_data.gyro.cord_y:.2f}, {imu_data.gyro.cord_z:.2f}] °/s"
        )


def update_flex_buffer(flex_data: FlexData) -> None:
    """
    Update the Flex sensor data buffer

    Args:
        flex_data: Flex sensor data object
    """
    global flex_seq_num

    seq_num = flex_data.seq_num
    logger.debug(f"Flex packet seq_num: {seq_num}")

    # Check data packet sequence number continuity
    if flex_seq_num is not None:
        # Handle normal increment and duplicate sequence number conditions
        if seq_num < flex_seq_num:
            logger.warning(f"Data sequence backward: expected >= {flex_seq_num + 1}, got {seq_num}")
        elif seq_num > flex_seq_num + 1:
            logger.warning(f"Data sequence gap: expected {flex_seq_num + 1}, got {seq_num}")
        elif seq_num == flex_seq_num:
            logger.debug(f"Duplicate sequence number: {seq_num}")
            return  # Skip duplicate packet

    flex_seq_num = seq_num

    # Split the channel data into individual channels
    channel_values = np.array_split(flex_data.channel_values, NUM_CHANNELS)

    # Update the data buffer for each channel
    for i in range(NUM_CHANNELS):
        flex_values[i] = np.roll(flex_values[i], -1)  # Roll the data to the left
        flex_values[i, -1] = channel_values[i][0]  # Append the latest data point


def on_flex_data(data: List[List[float]]) -> None:
    """
    Callback function to handle incoming Flex sensor data
    """
    logger.debug(f"Got flex callback len={len(data)}")

    if len(data) == 0:
        return

    flex_data_list = []
    for row in data:
        flex_data = FlexData.from_data(row)
        flex_data_list.append(flex_data)
        update_flex_buffer(flex_data)

    print_flex_timestamps(flex_data_list)


def print_flex_timestamps(data: List[FlexData]) -> None:
    """
    Elegant single-line printing of Flex data batch summary to avoid verbose outputs

    Args:
        data: Flex data list
    """
    if not data:
        return

    first_seq = data[0].seq_num
    last_seq = data[-1].seq_num
    seq_range = f"{first_seq}" if first_seq == last_seq else f"{first_seq} ~ {last_seq}"

    logger.info(
        f"-> Received {len(data)} Flex packets (seq: {seq_range})"
    )


async def connect_device():
    """
    Connect to the glove device and start the data stream

    Returns:
        EduDevice: Returns the device instance if connection succeeds, None otherwise
    """
    port_name = get_glove_port_name()
    if port_name is None:
        logger.error("No glove device found")
        return None

    try:
        device = libedu.EduDevice(port_name, BAUDRATE)
        parser = libedu.MessageParser("Glove-device", libedu.MsgType.Edu)

        # Configure sensor parameters using SensorProfile
        profile = libedu.SensorProfile(
            flex_rate=libedu.SamplingRate.SAMPLING_RATE_50,
            imu_rate=libedu.ImuSampleRate.IMU_SR_100,
            imu_data_type=libedu.UploadDataType.CALIBRATED_DATA,
            mag_rate=libedu.MagSampleRate.MAG_SR_20,
            mag_data_type=libedu.UploadDataType.CALIBRATED_DATA
        )

        await device.start_stream(parser, profile)
        logger.info("Listening for messages")

        # Get device status info
        await device.get_dongle_pair_stat()
        await asyncio.sleep(0.1)

        return device

    except Exception as e:
        logger.error(f"Failed to connect device: {e}")
        return None


def initialize_configuration() -> None:
    """
    Initialize the SDK configuration
    """
    logger.info("Initializing configuration...")
    libedu.set_msg_resp_callback(
        lambda device_id, msg: logger.debug(f"Message response from {device_id}: {msg}")
    )
    libedu.set_flex_data_callback(on_flex_data)
    libedu.set_imu_data_callback(on_imu_data)
    libedu.set_imu_calibration_data_callback(on_imu_data)
    libedu.set_mag_data_callback(on_mag_data)
    libedu.set_mag_calibration_data_callback(on_mag_data)


async def main() -> None:
    """
    Main function: initialize configurations, connect the device, and start the data collection loop
    """
    initialize_configuration()

    device = await connect_device()
    if device is not None:
        logger.info("Device setup completed successfully")
    else:
        logger.error("Failed to setup device")
        return

    logger.info("Starting data collection loop...")
    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Data collection stopped by user")
    except Exception as e:
        logger.error(f"Error in data collection loop: {e}")
        raise e
    finally:
        logger.info("Stopping sensor data stream and releasing serial port...")
        try:
            await device.stop_stream()
        except Exception as e:
            logger.error(f"Error stopping data stream: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Glove data collection program terminated.")

