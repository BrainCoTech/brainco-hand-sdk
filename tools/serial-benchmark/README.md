# Revo2 serial timing diagnostics

Compare raw Python serial I/O, raw C++ serial I/O, and SDK C++ queries on the same Linux host, port, and Revo2 device. The raw implementations use neither the SDK nor a Modbus library; they send the device's Modbus RTU request bytes directly.

[中文说明](README.zh.md)

## Scope and prerequisites

- Read motor status with function `04`, starting input register `2000 / 0x07D0`, count `24`.
- Use 460800 baud, 8N1, no software or hardware flow control. Supported address arguments are `126`, `127`, and `126,127`.
- Confirm the device model, register map, current baud rate, and addresses before running. Stop other users of the port; run these programs sequentially.
- Python requires PySerial. C++ uses Linux POSIX serial APIs and must be compiled on the target architecture. Linux x86_64 has been validated; Linux ARM requires target testing. This directory provides source code; supply the SDK library separately for the optional comparison.
- Queries are read-only. The optional `--low-latency` flag changes the host serial driver's setting and does not restore it on exit.

## Run the raw benchmarks

Run from this directory. Select the actual port, for example `/dev/ttyAMA0` or `/dev/ttyUSB0`.

```bash
python3 -m pip install -r requirements.txt
serial_port=/dev/ttyUSB0
python3 serial_test_read_speed.py "$serial_port" 460800 126 5 python-126.csv --low-latency
python3 serial_test_read_speed.py "$serial_port" 460800 127 5 python-127.csv --low-latency
python3 serial_test_read_speed.py "$serial_port" 460800 126,127 5 python-dual.csv --low-latency
```

Keep `bench_common.hpp` next to `serial_test_read_speed.cpp`. The raw C++ program needs no SDK headers or libraries:

```bash
g++ -std=c++17 -O2 -Wall -Wextra -Werror serial_test_read_speed.cpp -o serial_test_read_speed
serial_port=/dev/ttyUSB0
./serial_test_read_speed "$serial_port" 460800 126 5 cpp-126.csv --low-latency
./serial_test_read_speed "$serial_port" 460800 127 5 cpp-127.csv --low-latency
./serial_test_read_speed "$serial_port" 460800 126,127 5 cpp-dual.csv --low-latency
```

Arguments are `PORT BAUD SLAVES SECONDS CSV`, with a duration greater than zero and at most 60 seconds. Put the optional C++ flag last. `126,127` alternates requests within one connection; do not run two programs concurrently on that port.

## Low-latency setup

Without `--low-latency`, both raw programs preserve the current flag and print `requested=0 result=unchanged`. With it, they use Linux `TIOCGSERIAL` / `TIOCSSERIAL` directly to enable `ASYNC_LOW_LATENCY`, then read back the flags. No SDK is involved.

```text
LOW_LATENCY requested=1 result=flag_set flags_before=... flags_after=... timer_before_ms=16 timer_after_ms=1
```

- `flag_set` means the readback flag is set, either by this run or previously.
- `get_failed`, `set_failed`, `readback_failed`, or `flag_clear` produce a `WARN`. Queries continue; retain the warning and record the setup result with the measurements.
- The timer fields read the USB serial driver's `latency_timer`. FTDI may change it to 1 ms; check the actual readback.
- `unavailable` means that sysfs value could not be read. Hardware UARTs normally do not expose FTDI's timer; use the `result` field to check driver setup.

The effect of low-latency setup depends on the driver. If SDK initialization changes a setting, repeat the raw test with the same effective setting.

## Optional SDK C++ comparison

Supply SDK headers and libraries for the target architecture. Set `sdk_dist` to the absolute SDK `dist` path:

```bash
sdk_dist=/absolute/path/to/sdk/dist
g++ -std=c++17 -O2 -Wall -Wextra -Werror sdk_read_speed.cpp \
  -I "$sdk_dist/include" -L "$sdk_dist/shared/linux" \
  -Wl,-rpath,"$sdk_dist/shared/linux" -lbc_stark_sdk -o sdk_read_speed
ldd ./sdk_read_speed
serial_port=/dev/ttyUSB0
./sdk_read_speed "$serial_port" 460800 126 5 sdk-126.csv
./sdk_read_speed "$serial_port" 460800 127 5 sdk-127.csv
./sdk_read_speed "$serial_port" 460800 126,127 5 sdk-dual.csv
```

Check the loaded SDK path and record its package version. SDK initialization controls its own low-latency behavior, which can vary by version; this comparison program rejects the raw benchmark's `--low-latency` flag.

## Requests and validation

| Slave ID | Complete request, including CRC |
|---|---|
| 126 / 0x7E | `7E 04 07 D0 00 18 FB 42` |
| 127 / 0x7F | `7F 04 07 D0 00 18 FA 93` |

Each normal response is 53 bytes. Both raw implementations check the address, function, byte count, and CRC. C++ accumulates partial reads/writes; Python uses PySerial to read the complete response. The first query to each address allows up to one second for startup and reports `startup_ms`, without resending a timed-out request. Warm-up and measured transactions then use an approximately 100 ms boundary. A timeout, short response, or validation failure stops the run. Modbus RTU has no transaction sequence number: ensure there is no other master or outstanding request from a previous run before starting.

## Interpret results

Startup prints settings and the first raw request/response. Measurement follows warm-up, with no printing or deliberate sleep inside the loop. Samples are written to CSV afterward; the last JSON line reports:

| Field | Meaning |
|---|---|
| `successes` / `failures` | Successful transactions and failures |
| `rpc_hz` | Total successful queries per second across all addresses |
| `per_hand_hz` | Complete cycles per second; equals each hand's rate in an error-free alternating run |
| `median_ms` / `p95_ms` / `max_ms` | Duration distribution for successful calls |
| `timer_before` / `timer_after` | Timer readback around measurement, after optional setup |

Raw timing includes constructing, sending, receiving, and validating a request. SDK timing includes the status API call and freeing its result. These are host call durations, not device processing time alone. Statistics exclude startup and warm-up; inspect `startup_ms` separately. Opening or warm-up failures may exit without producing a statistics JSON record.

If both raw implementations are faster than the SDK, inspect the loaded library and its initialization, read, and scheduling paths. If all three are slow, inspect shared driver, link, and device conditions. If raw Python and raw C++ differ, first compare serial settings and read behavior. Keep the host, device, parameters, and effective settings matched and repeat the comparison.

Save full terminal output and CSV, along with the port, baud rate, addresses, firmware, SDK version, and effective low-latency settings. `2>&1 | tee run.log` includes warnings in the saved output.
