# Python Examples

Python examples for Revo1/Revo2 devices. New-generation Python examples live in the dedicated SDK.

## Layout

- `demo/` - shared demos for auto-detect, hand control, monitor, DFU
- `revo1/` - Revo1 examples
- `revo2/` - Revo2 examples
- `revo1_can/`, `revo2_can/`, `revo2_canfd/`, `revo2_ethercat/` - protocol-specific examples
- `gui/` - Python GUI

## Install and discover devices

Use Python 3.9 or later on Windows x64 or Linux x86_64/ARM64. The `2.0.7`
Linux wheels require glibc 2.31 or later (Ubuntu 20.04+). No macOS Python wheel
is provided for this release.

From this directory, install the SDK and example dependencies:

```bash
python -m pip install -r requirements.txt
```

To install SDK `2.0.7` from the OSS mirror instead:

```bash
bash install_whl.sh 2.0.7
```

Close other programs using the serial port, then run read-only discovery:

```bash
cd demo
python auto_detect.py
```

SDK `2.0.7` fixes discovery skipping usable FTDI RS485 channels that share a USB
serial number. If another application connects but automatic discovery fails,
replace the SDK call inside `main()` in `demo/auto_detect.py` with an explicit
port and protocol:

```python
devices = await sdk.auto_detect(port="COM5", protocol="Modbus")
```

Replace `COM5` with the working port; on Linux use a path such as `/dev/ttyUSB0`.
This bypasses automatic port filtering. If it still fails, compare the baud rate,
slave ID, and serial settings with the working application. The port must be free
before running the example. Check the SDK version reported in the runtime log;
the installed package version alone does not prove which native library was loaded.

The example stops after finding the first device. Use `scan_all=True` in the SDK
call when you need all supported device addresses in the scanner's search set;
this does not scan every possible slave ID.
