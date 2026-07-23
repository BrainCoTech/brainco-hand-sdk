# Revo2 EtherCAT Python SDK

## Requirement

- Python 3.9~3.12
- Linux: Ubuntu 20.04/22.04 LTS (x86_64/aarch64), glibc ≥ 2.31
- EtherCAT Master (IgH EtherCAT Master) installed and configured

## Usage

```shell
cd python

# Install dependencies
# Option 1: Conda / pip
pip install -e .

# Option 2: uv
uv sync

## EtherCAT Communication Protocol
cd revo2_ethercat
python ec_sdo.py # SDO read/configure
python ec_pdo.py # PDO read joint status, control device
python ec_dfu.py # Firmware OTA
```
