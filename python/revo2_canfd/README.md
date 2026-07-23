# Revo2 CANFD Python SDK

## Requirement

- Python 3.9~3.12
- Linux: Ubuntu 20.04/22.04 LTS (x86_64/aarch64), glibc ≥ 2.31
- macOS: 10.15+ (ZQWL only)
- Windows: 10/11

## Usage

```shell
cd python

# Install dependencies
# Option 1: Conda / pip
pip install -e .

# Option 2: uv
uv sync

## CANFD Communication Protocol
cd revo2_canfd

# ZLG USBCAN-FD device, supports Windows and Linux
python zlg_canfd.py # Read device info, control device
python zlg_canfd_touch_pressure.py # Pressure-sensitive tactile hand example

# SocketCAN (Linux)
STARK_SOCKETCAN_IFACE=can0 python socketcan_canfd.py # Read device info, control device
STARK_SOCKETCAN_IFACE=can0 STARK_SLAVE_ID=0x7f python socketcan_canfd.py # Select slave id
STARK_SOCKETCAN_IFACE=can0 python socketcan_canfd_touch_pressure.py # Touch pressure example
STARK_SOCKETCAN_IFACE=can0 python socketcan_canfd_dfu.py # Firmware OTA
```
