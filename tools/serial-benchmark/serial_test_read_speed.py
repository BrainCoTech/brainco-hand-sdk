"""Read-only Revo2 serial benchmark; no SDK or Modbus package is imported."""
import argparse
import array
import csv
import fcntl
import json
import math
from pathlib import Path
import sys
import termios
import time

import serial


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def request(slave):
    frame = bytes([slave, 4, 7, 0xD0, 0, 24])
    return frame + crc16(frame).to_bytes(2, "little")


def timer_value(port):
    try:
        return (Path("/sys/bus/usb-serial/devices") / Path(port).name / "latency_timer").read_text().strip()
    except OSError:
        return "unavailable"


def configure_low_latency(port, requested):
    timer_before = timer_value(port.port)
    if not requested:
        print(f"LOW_LATENCY requested=0 result=unchanged timer_ms={timer_before}", flush=True)
        return
    # Linux serial_struct begins with five 32-bit fields; flags is field 4.
    # Reserve enough storage for both 32-bit and 64-bit layouts.
    serial_info = array.array("i", [0] * 32)
    if serial_info.itemsize != 4:
        raise RuntimeError("Unsupported native int size for Linux serial_struct")
    try:
        fcntl.ioctl(port.fileno(), 0x541E, serial_info)
    except OSError as exc:
        print(f"WARN low_latency result=get_failed error={exc}", file=sys.stderr)
        print(f"LOW_LATENCY requested=1 result=get_failed timer_ms={timer_value(port.port)}", flush=True)
        return
    before_flags = serial_info[4]
    serial_info[4] |= 0x2000
    try:
        if serial_info[4] != before_flags:
            fcntl.ioctl(port.fileno(), 0x541F, serial_info)
    except OSError as exc:
        print(f"WARN low_latency result=set_failed error={exc}", file=sys.stderr)
        print(f"LOW_LATENCY requested=1 result=set_failed flags_before={before_flags} "
              f"timer_before_ms={timer_before} timer_after_ms={timer_value(port.port)}", flush=True)
        return
    try:
        fcntl.ioctl(port.fileno(), 0x541E, serial_info)
    except OSError as exc:
        print(f"WARN low_latency result=readback_failed error={exc}", file=sys.stderr)
        print(f"LOW_LATENCY requested=1 result=readback_failed timer_after_ms={timer_value(port.port)}", flush=True)
        return
    flag_set = bool(serial_info[4] & 0x2000)
    if not flag_set:
        print("WARN low_latency flag is clear after setup", file=sys.stderr)
    result = "flag_set" if flag_set else "flag_clear"
    print(f"LOW_LATENCY requested=1 result={result} flags_before={before_flags} "
          f"flags_after={serial_info[4]} timer_before_ms={timer_before} "
          f"timer_after_ms={timer_value(port.port)}", flush=True)


def query(port, slave, timeout=0.1):
    deadline = time.perf_counter() + timeout
    frame = request(slave)
    if port.write(frame) != len(frame):
        raise RuntimeError("Incomplete request write")
    response = port.read(53)
    if len(response) != 53:
        raise RuntimeError(f"Incomplete response: {len(response)} bytes, hex={response.hex()}")
    if time.perf_counter() > deadline:
        raise TimeoutError("Transaction deadline exceeded")
    if response[:3] != bytes([slave, 4, 48]) or crc16(response) != 0:
        raise RuntimeError(f"Invalid response address/function/byte count/CRC: {response.hex()}")
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port")
    parser.add_argument("baud", type=int)
    parser.add_argument("slaves", help="126, 127, or 126,127")
    parser.add_argument("seconds", type=float)
    parser.add_argument("csv")
    parser.add_argument("--low-latency", action="store_true",
                        help="Try Linux ASYNC_LOW_LATENCY and report the readback; no SDK is used")
    args = parser.parse_args()
    slaves = [int(value) for value in args.slaves.split(",")]
    if args.baud != 460800 or not slaves or len(slaves) > 2 or len(set(slaves)) != len(slaves):
        parser.error("Use 460800 baud and unique Revo2 slave addresses")
    if any(slave not in (126, 127) for slave in slaves) or not math.isfinite(args.seconds) or not 0 < args.seconds <= 60:
        parser.error("Only addresses 126/127 and durations in (0,60] are allowed")
    if request(126).hex() != "7e0407d00018fb42" or request(127).hex() != "7f0407d00018fa93":
        raise RuntimeError("Request differs from known Revo2 query frame")
    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=0.1,
                       bytesize=8, parity="N", stopbits=1, xonxoff=False,
                       rtscts=False, dsrdtr=False, exclusive=True) as port:
        fcntl.ioctl(port.fileno(), termios.TIOCEXCL)
        port.reset_input_buffer()
        configure_low_latency(port, args.low_latency)
        # Allow driver setup to settle without resending a timed-out request.
        port.timeout = 1.0
        for slave in slaves:
            before = time.perf_counter()
            response = query(port, slave, timeout=1.0)
            startup_ms = (time.perf_counter()-before)*1000
            print(f"FIRST_FRAME slave={slave} startup_ms={startup_ms:.3f} "
                  f"tx={request(slave).hex()} rx={response.hex()}", flush=True)
        port.timeout = 0.1
        for _ in range(20):
            for slave in slaves:
                query(port, slave)
        timer_before = timer_value(args.port)
        samples = []
        failures = cycles = 0
        error = None
        start = time.perf_counter()
        while time.perf_counter() - start < args.seconds:
            for slave in slaves:
                before = time.perf_counter()
                ok = True
                try:
                    query(port, slave)
                except (OSError, RuntimeError, serial.SerialException) as exc:
                    failures += 1
                    ok = False
                    error = str(exc)
                end = time.perf_counter()
                samples.append((slave, before-start, (end-before)*1000, int(ok)))
                if not ok:
                    break
            if failures:
                break
            cycles += 1
        elapsed = time.perf_counter() - start
        timer_after = timer_value(args.port)
    with open(args.csv, "w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["slave", "start_s", "elapsed_ms", "success"])
        writer.writerows(samples)
    durations = sorted(row[2] for row in samples if row[3])
    def percentile(p):
        return durations[int(p*(len(durations)-1))] if durations else 0
    print(json.dumps({"backend": "raw_python", "slaves": slaves,
                      "timer_before": timer_before, "timer_after": timer_after,
                      "cycles": cycles, "successes": len(durations), "failures": failures,
                      "elapsed_s": elapsed, "rpc_hz": len(durations)/elapsed,
                      "per_hand_hz": cycles/elapsed, "median_ms": percentile(.5),
                      "p95_ms": percentile(.95), "max_ms": percentile(1)}), flush=True)
    if failures:
        print(f"Transaction failed; stopping to avoid stale-response reuse: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
