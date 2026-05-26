"""
Armband EMG Data Collection Example

This example demonstrates how to connect to the armband device and collect EMG (electromyography) data,
while also supporting the collection of IMU and magnetometer data.
"""

import asyncio
import numpy as np
import os
from filters_sdk import *
from model import EMGData
from edu_utils import *

# Configuration constants
SAMPLING_FREQUENCY = 250  # EMG sampling frequency (Hz)
NUM_CHANNELS = 8  # Number of EMG channels
EMG_BUFFER_LENGTH = 1250  # EMG data buffer length (number of data points)
FETCH_DATA_COUNT = 100  # Number of data points fetched each time
BAUDRATE = 115200  # Serial port baudrate
DATA_PRINT_INTERVAL = 0.5  # Data print interval (seconds)

# Global variables
emg_values = np.zeros((NUM_CHANNELS, EMG_BUFFER_LENGTH))  # EMG sensor data buffer

def update_emg_buffer(emg_data: EMGData) -> None:
    """
    Update the EMG sensor data buffer

    Args:
        emg_data: EMG data object
    """
    # Split the channel data into individual channels
    channel_values = np.array_split(emg_data.channel_values, NUM_CHANNELS)

    # Update the data buffer for each channel
    for i in range(NUM_CHANNELS):
        emg_values[i] = np.roll(emg_values[i], -1)  # Roll the data to the left
        raw_value = channel_values[i][0]
        emg_values[i, -1] = raw_value  # Append the latest data point

        # filter_value = env_noise_50[i].filter(raw_value)
        # filter_value = env_noise_60[i].filter(filter_value)
        # filter_value = hp[i].filter(filter_value)
        # logger.info(f"Channel {i} raw value: {raw_value}, filtered value: {filter_value}")
        # emg_values[i, -1] = filter_value  # Append the latest data point


def print_all_sensor_data() -> None:
    """
    Fetch and print all sensor data (EMG, IMU, MAG, and EULER)
    """
    # 1. Fetch and process EMG data
    emg_buff = libedu.get_emg_buffer(FETCH_DATA_COUNT, clean=True)
    if len(emg_buff) > 0:
        emg_data_list = []
        for row in emg_buff:
            emg_data = EMGData.from_data(row)
            emg_data_list.append(emg_data)
            update_emg_buffer(emg_data)
        
        # Print EMG data timestamp information
        print_emg_timestamps(logger, emg_data_list)

    # 2. Fetch and process IMU calibrated data
    imu_calibration_buff = libedu.get_imu_calibration_buff(FETCH_DATA_COUNT, clean=True)
    imu_str = ""
    if len(imu_calibration_buff) > 0:
        first_imu_seq = int(imu_calibration_buff[0][0])
        last_imu_seq = int(imu_calibration_buff[-1][0])
        latest_imu = imu_calibration_buff[-1]
        
        # Format values to integers for cleaner logs
        acc_vals = [int(latest_imu[1]), int(latest_imu[2]), int(latest_imu[3])]
        gyro_vals = [int(latest_imu[4]), int(latest_imu[5]), int(latest_imu[6])]
        
        imu_seq_range = f"{first_imu_seq}" if first_imu_seq == last_imu_seq else f"{first_imu_seq} ~ {last_imu_seq}"
        imu_str = f"IMU x{len(imu_calibration_buff)} (seq: {imu_seq_range} | acc: {acc_vals} | gyro: {gyro_vals})"

    # 3. Fetch and process MAG calibrated data
    mag_calibration_buff = libedu.get_mag_calibration_buff(FETCH_DATA_COUNT, clean=True)
    mag_str = ""
    if len(mag_calibration_buff) > 0:
        first_mag_seq = int(mag_calibration_buff[0][0])
        last_mag_seq = int(mag_calibration_buff[-1][0])
        latest_mag = mag_calibration_buff[-1]
        
        mag_vals = [int(latest_mag[1]), int(latest_mag[2]), int(latest_mag[3])]
        
        mag_seq_range = f"{first_mag_seq}" if first_mag_seq == last_mag_seq else f"{first_mag_seq} ~ {last_mag_seq}"
        mag_str = f"MAG x{len(mag_calibration_buff)} (seq: {mag_seq_range} | mag: {mag_vals})"

    # 4. Fetch and process Euler angle data
    euler_buff = libedu.get_euler_buffer(FETCH_DATA_COUNT, clean=True)
    euler_str = ""
    if len(euler_buff) > 0:
        first_euler_seq = int(euler_buff[0][0])
        last_euler_seq = int(euler_buff[-1][0])
        latest_euler = euler_buff[-1]
        
        yaw, pitch, roll = latest_euler[1], latest_euler[2], latest_euler[3]
        euler_seq_range = f"{first_euler_seq}" if first_euler_seq == last_euler_seq else f"{first_euler_seq} ~ {last_euler_seq}"
        euler_str = f"EULER x{len(euler_buff)} (seq: {euler_seq_range} | yaw: {yaw:.2f} | pitch: {pitch:.2f} | roll: {roll:.2f})"

    # Combine IMU, MAG, and EULER into a single-line print if they exist
    parts = []
    if imu_str: parts.append(imu_str)
    if mag_str: parts.append(mag_str)
    if euler_str: parts.append(euler_str)
    if parts:
        logger.info("-> Received " + " | ".join(parts))

async def setup_armband_device() -> bool:
    """
    Setup and connect the armband device

    Returns:
        bool: Returns True if connection succeeds, False otherwise
    """
    # Get the armband device port (auto-detect or manually specify)
    libedu.get_usb_available_ports()
    port_name = get_armband_port_name()

    # If auto-detection fails, manually specify the port
    if port_name is None:
        # port_name = "COM8"  # Windows
        # port_name = "/dev/tty.usbmodem212201"  # macOS/Linux
        logger.warning(f"Using manual port: {port_name}")

    if port_name is None:
        logger.error("No armband device found")
        return False

    try:
        device = libedu.PyEduDevice(port_name, BAUDRATE)

        # Open the serial port and start the background parsing stream
        await device.start_data_stream(libedu.MessageParser("ARMBAND-device", libedu.MsgType.Edu))
        logger.info("Serial port opened, background parser started")

        # Query device information
        await device.get_device_info()
        await asyncio.sleep(0.5)

        # Query pairing status
        await device.get_dongle_pair_stat()
        await asyncio.sleep(0.5)

        # Configure sensor parameters
        await configure_sensors(device)

        # Send the start data collection command to the device
        await device.start_sensor_data_stream()
        logger.info("Sensor data stream started")

        logger.info("Armband device setup completed successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to setup armband device: {e}")
        return False


async def configure_sensors(device) -> None:
    """
    Configure sensor sampling rates and data types

    Args:
        device: Device object
    """
    # Set the EMG sampling rate to 250Hz, 0xFF means all channels are enabled
    await device.set_emg_config(libedu.AfeSampleRate.AFE_SR_250, 0xFF)

    # Configure IMU sensor - returns calibrated data
    await device.set_imu_config(
        libedu.ImuSampleRate.IMU_SR_100,
        libedu.UploadDataType.CALIBRATED_DATA
    )

    # Configure magnetometer sensor - returns calibrated data
    await device.set_mag_config(
        libedu.MagSampleRate.MAG_SR_20,
        libedu.UploadDataType.CALIBRATED_DATA
    )

    # Optional: returns raw data
    # await device.set_imu_config(libedu.ImuSampleRate.IMU_SR_100, libedu.UploadDataType.RAW_DATA)
    # await device.set_mag_config(libedu.MagSampleRate.MAG_SR_20, libedu.UploadDataType.RAW_DATA)

    logger.info("Sensor configuration completed")


def initialize_configuration() -> None:
    """
    Initialize the SDK configuration
    """
    logger.info("Initializing EMG configuration...")
    libedu.set_emg_buffer_cfg(EMG_BUFFER_LENGTH)
    libedu.set_msg_resp_callback(
        lambda device_id, msg: logger.warning(f"Message response from {device_id}: {msg}")
    )
    
    # Register Euler Angle callback demo
    libedu.set_euler_data_callback(
        lambda data: logger.info(f"⚡ [Euler Callback] Received {len(data)} packets. Latest: Yaw={data[-1][1]:.2f}, Pitch={data[-1][2]:.2f}, Roll={data[-1][3]:.2f}") if data else None
    )


async def main() -> None:
    """
    Main function: initialize configurations, connect the device, and start the EMG data collection loop
    """
    initialize_configuration()

    if await setup_armband_device():
        logger.info("Armband device setup completed successfully")
    else:
        logger.error("Failed to setup armband device")
        return

    logger.info("Starting EMG data collection loop...")
    try:
        while True:
            print_all_sensor_data()
            await asyncio.sleep(DATA_PRINT_INTERVAL)
    except KeyboardInterrupt:
        logger.info("EMG data collection stopped by user")
    except Exception as e:
        logger.error(f"Error in data collection loop: {e}")


if __name__ == "__main__":
    asyncio.run(main())
