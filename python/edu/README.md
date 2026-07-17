# Educational Device SDK Python Examples

This directory contains Python examples and Graphical User Interfaces (GUIs) demonstrating how to connect, configure, and collect real-time data from **BrainCo Armband** and **Glove** devices using the `bc-edu-sdk`.

---

## 🛠️ Environment Setup (Highly Recommended: Conda)

For runtime stability and dependency isolation, it is **highly recommended** to use a **Conda virtual environment** running **Python 3.10+**.

### 1. Create and Activate Virtual Environment
```shell
# Create a new conda environment named py310 with Python 3.10
conda create -n py310 python=3.10 -y

# Activate the environment
conda activate py310
```

### 2. Verify Your Environment
```shell
# Verify that python points to the correct Conda path
which python

# Output should resemble:
# /path/to/miniconda/envs/py310/bin/python

# Check the Python version (Python 3.10.x is recommended)
python -V
```

### 3. Install Dependencies
```shell
# Install the required packages via PyPI simple index
uv sync
```

*Note: If automated installation fails, you can manually download the compiled wheel from [PyPI - bc-edu-sdk](https://pypi.org/project/bc-edu-sdk/) and install it locally:*
```shell
pip install --force-reinstall '/path/to/bc_edu_sdk.whl'
```

---

## 📂 Project Structure & Demos

### 1. Console Data Stream Demos (CLI)
Real-time optimized telemetry loggers that print calibrated raw and sensor outputs in a clean single-line format:
- **One-Key Profile Stream Example (Recommended)**: Connects to the Stark armband and starts data streaming in a single high-level call using `SensorProfile`. Demonstrates one-key parameter hot-reloading dynamically.
  ```shell
  python start_stream_profile.py
  ```
- **Glove Example**: Connects to the Glove device via USB receiver dongle to stream Flex (bending), IMU, and Magnetometer data.
  ```shell
  python glove_example.py
  ```
- **Armband Example**: Connects to the Stark armband device and streams multi-sensor telemetry using the recommended high-level API with robust lifecycle guards.
  ```shell
  python armband_example.py
  ```

### 2. Advanced Signal Analysis & Filtering
- **EMG Filtering & Visualization Demo**: Collects EMG signals, applies 50Hz/60Hz grid notch filters and 10Hz highpass filters in real-time, and saves comparison plots locally under the `plots/` directory.
  ```shell
  python armband_filter_demo.py
  ```
- **IMU & Magnetometer Calibration Utility**: Collects RAW IMU/MAG samples and writes gyro zero-bias plus magnetometer calibration parameters back to the device. Defaults to armband; pass `--device glove` for glove hardware.
  ```shell
  python imu_mag_calibration.py --device armband
  python imu_mag_calibration.py --device glove --imu-only
  ```
- **Armband Serial DFU Utility**: Uploads a firmware package over the armband serial link and reports transfer progress.
  ```shell
  python armband_serial_dfu.py path/to/firmware.ota
  ```

### 3. Desktop Workstation Interfaces (GUI)
Comprehensive PyQt-based dashboards displaying high-frequency real-time charts:
- **Armband GUI**: Visualizes real-time EMG waveforms, frequency domains (FFT), and multi-channel IMU acceleration/gyroscopes.
  ```shell
  python armband_gui.py
  ```
- **Glove GUI**: Renders dynamic timelines for all 6-channel Flex sensors, 3D IMU coordinates, and Magnetometer calibration values.
  ```shell
  python glove_gui.py
  ```

## 🤖 EMG Gesture Training & Robotic Control Flow

To control robotic arms or smart hands via EMG gesture classification:
1. **Gather Samples**: Collect EMG training datasets for desired hand gestures (suggested: 3 trials per gesture, 5 seconds per trial) using the Armband dashboard.
2. **Train Classification**: Feed the collected buffers into your classification model to output gesture commands.
3. **Control Output**: Stream the predicted gestures as execution frames to command the robotic hand actuators.
