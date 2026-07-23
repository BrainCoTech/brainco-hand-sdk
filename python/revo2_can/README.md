# Revo2 CAN Python SDK

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

## CAN Communication Protocol
cd revo2_can

# ZLG CAN device, supports Windows and Linux
python zlg_can.py # Read device info, control device

# SocketCAN (Linux)
STARK_SOCKETCAN_IFACE=can0 python socketcan_can.py # Read device info, control device
```
