"""
Armband EMG Filtering & Visualization Demo

This advanced example demonstrates how to use the bc-edu-sdk to collect EMG electromyography
signals from the armband device and apply the built-in Butterworth filters to perform
50Hz/60Hz grid notch filtering and 10Hz highpass filtering.
After collecting 1250 sample points (approx. 5 seconds of data), it uses matplotlib to
automatically generate and save a comparison waveform plot of channel 1 before and after filtering,
demonstrating the denoising capabilities of the filtering algorithms.

Dependencies:
pip install matplotlib numpy bc-edu-sdk
"""

import asyncio
import numpy as np
import os
import matplotlib.pyplot as plt

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

# Filters
env_noise_50 = [BWBandStopFilter(4, sample_rate=SAMPLING_FREQUENCY, fl=49, fu=51) for _ in range(NUM_CHANNELS)]
env_noise_60 = [BWBandStopFilter(4, sample_rate=SAMPLING_FREQUENCY, fl=59, fu=61) for _ in range(NUM_CHANNELS)]
hp = [BWHighPassFilter(4, sample_rate=SAMPLING_FREQUENCY, f=10) for _ in range(NUM_CHANNELS)]


def save_channel_plot():
    """
    Save a comparison plot of channel 1 raw and filtered data once sample count exceeds 1250
    """
    if emg_values.shape[1] < 1250:
        return

    raw_data = emg_values[0].copy()
    filtered = raw_data.copy()
    for i in range(len(filtered)):
        filtered[i] = env_noise_50[0].filter(filtered[i])
        filtered[i] = env_noise_60[0].filter(filtered[i])
        filtered[i] = hp[0].filter(filtered[i])

    logger.info(f"Plotting: filtered first 5 values={filtered[:5]}")
    plt.figure(figsize=(10, 4))
    plt.plot(raw_data, label="Raw Data (Contains 50Hz/60Hz Grid Noise & Baseline Drift)")
    plt.plot(filtered, label="Filtered Data (Butterworth Highpass & Bandstop Applied)")
    plt.title("Channel 1 EMG Data - Butterworth Filtering Waveform Comparison")
    plt.xlabel("Sample Point")
    plt.ylabel("Amplitude (uV)")
    plt.legend()
    plt.tight_layout()

    # Automatically rotate and save into the first 10 file indices
    save_dir = "plots"
    os.makedirs(save_dir, exist_ok=True)
    file_count = len(os.listdir(save_dir))
    filename = os.path.join(save_dir, f"channel1_plot_{(file_count) % 10}.png")
    plt.savefig(filename)
    plt.close()
    logger.info(f"🎨 Waveform plot successfully saved to: {filename}")


def update_emg_buffer(emg_data: EMGData) -> None:
    """
    Update the EMG sensor data buffer
    """
    channel_values = np.array_split(emg_data.channel_values, NUM_CHANNELS)
    for i in range(NUM_CHANNELS):
        emg_values[i] = np.roll(emg_values[i], -1)  # Roll the data to the left
        raw_value = channel_values[i][0]
        emg_values[i, -1] = raw_value  # Append the latest data point


def print_emg_data() -> None:
    """
    Fetch, process, and print EMG signals
    """
    emg_buff = libedu.get_emg_buffer(FETCH_DATA_COUNT, clean=True)
    
    # Log buffer count in debug level to reduce console noise
    logger.debug(f"Got EMG buffer len={len(emg_buff)}")

    if len(emg_buff) == 0:
        return

    emg_data_list = []
    for row in emg_buff:
        emg_data = EMGData.from_data(row)
        emg_data_list.append(emg_data)
        update_emg_buffer(emg_data)

    # Print elegant summary timestamp info
    print_emg_timestamps(logger, emg_data_list)

    # Offline plot saving
    save_channel_plot()


async def setup_armband_device() -> bool:
    """
    Setup and connect the armband device
    """
    libedu.get_usb_available_ports()
    port_name = get_armband_port_name()

    if port_name is None:
        logger.error("No armband device found. Please plug in the receiver dongle.")
        return False

    try:
        device = libedu.PyEduDevice(port_name, BAUDRATE)

        # Open the serial port and start the background parsing stream
        await device.start_data_stream(libedu.MessageParser("ARMBAND-device", libedu.MsgType.Edu))
        logger.info("Serial port opened, background parser started")

        # Query device info and dongle pairing status
        await device.get_device_info()
        await asyncio.sleep(0.5)
        await device.get_dongle_pair_stat()
        await asyncio.sleep(0.5)

        # Configure sensor sampling rates
        await device.set_emg_config(libedu.AfeSampleRate.AFE_SR_250, 0xFF)
        await device.set_imu_config(libedu.ImuSampleRate.IMU_SR_100, libedu.UploadDataType.CALIBRATED_DATA)
        await device.set_mag_config(libedu.MagSampleRate.MAG_SR_20, libedu.UploadDataType.CALIBRATED_DATA)
        logger.info("Sensor configurations applied successfully")

        # Start sensor data stream
        await device.start_sensor_data_stream()
        logger.info("Sensor data stream started")
        return True

    except Exception as e:
        logger.error(f"Failed to setup armband device: {e}")
        return False


def initialize_configuration() -> None:
    """
    Initialize the SDK configuration
    """
    logger.info("Initializing EMG configuration...")
    libedu.set_emg_buffer_cfg(EMG_BUFFER_LENGTH)
    libedu.set_msg_resp_callback(
        lambda device_id, msg: logger.debug(f"Message response from {device_id}: {msg}")
    )


async def main() -> None:
    """
    Main function: initialize configurations, connect the device, and start the EMG collection loop
    """
    initialize_configuration()

    if await setup_armband_device():
        logger.info("Armband device setup completed successfully. Waiting for EMG packets...")
    else:
        logger.error("Failed to setup armband device")
        return

    logger.info("Starting EMG data collection loop...")
    try:
        while True:
            print_emg_data()
            await asyncio.sleep(DATA_PRINT_INTERVAL)
    except KeyboardInterrupt:
        logger.info("EMG data collection stopped by user")
    except Exception as e:
        logger.error(f"Error in data collection loop: {e}")


if __name__ == "__main__":
    asyncio.run(main())
