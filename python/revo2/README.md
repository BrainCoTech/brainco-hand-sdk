# Revo2 Python SDK (RS-485/Modbus)

## Requirement

- Python 3.9~3.12
- Linux: Ubuntu 20.04/22.04 LTS (x86_64/aarch64), glibc ≥ 2.31
- macOS: 10.15+
- Windows: 10/11

## Usage

```shell
cd python

# Install dependencies
# Option 1: Conda / pip
pip install -e .

# Option 2: uv
uv sync

cd revo2
# Control/read info - single hand
python revo2_ctrl.py
# Control/read info - single hand (capacitive tactile hand)
python revo2_touch.py
# Control/read info - single hand (pressure-sensitive tactile hand)
python revo2_touch_pressure.py
# Control/read info - multiple hands
python revo2_ctrl_multi.py
# Control dual hands
python revo2_ctrl_dual.py
# Action sequences
python revo2_action_seq.py
# Update configuration, modify device ID, baud rate, Turbo mode, etc.
python revo2_cfg.py
```
