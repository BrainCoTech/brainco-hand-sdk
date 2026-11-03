#!/usr/bin/env python3
"""Revo2 diagnostics through the installed BrainCo SDK's Linux SocketCAN transport."""
import argparse
import asyncio
import collections
import datetime
import hashlib
import importlib.metadata
import json
import logging
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

POSES = {'open': [0, 0, 0, 0, 0, 0], 'close': [500, 500, 1000, 1000, 1000, 1000]}


def sdk_identity(sdk):
    native = Path(sdk.__file__).resolve()
    try:
        distribution = importlib.metadata.version('bc-stark-sdk')
    except importlib.metadata.PackageNotFoundError:
        distribution = None
    return dict(python_executable=sys.executable, python_version=platform.python_version(),
                platform=platform.platform(), architecture=platform.machine(),
                distribution_version=distribution, sdk_version=sdk.get_sdk_version(),
                native_module_path=str(native),
                native_module_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def interface_state(interface):
    try:
        result = subprocess.run(['ip', '-details', '-statistics', 'link', 'show', 'dev', interface],
                                capture_output=True, text=True, timeout=5)
        return dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(error=str(error))


def motor_values(status):
    result = {}
    for name in ('positions', 'speeds', 'currents', 'states'):
        values = list(getattr(status, name))
        if len(values) != 6:
            raise ValueError(f'{name} requires 6 values, received {len(values)}')
        result[name] = [str(value) if name == 'states' else int(value) for value in values]
    return result


def info_values(info):
    return dict(serial_number=info.serial_number, firmware_version=info.firmware_version,
                hand_type=str(info.hand_type), hardware_type=str(info.hardware_type),
                description=str(info.description))


class Recorder:
    def __init__(self, path):
        self.handle = path.open('x', encoding='utf-8')
        self.sequence = 0
        self.counts = collections.Counter(attempts=0, successes=0, failures=0)
        self.errors = collections.Counter()

    def emit(self, event, **fields):
        self.handle.write(json.dumps(dict(event=event,
            utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            monotonic_ns=time.monotonic_ns(), **fields), ensure_ascii=True) + '\n')
        self.handle.flush()

    async def call(self, slave, operation, factory, convert):
        self.sequence += 1
        sequence = self.sequence
        self.emit('api_start', sequence=sequence, slave=slave, operation=operation)
        self.counts['attempts'] += 1
        start = time.monotonic()
        try:
            value = await factory()
            converted = convert(value)
        except Exception as error:
            message = f'{type(error).__name__}: {error}'
            self.errors[message] += 1
            self.counts['failures'] += 1
            self.emit('api_error', sequence=sequence, slave=slave, operation=operation,
                      latency_ms=(time.monotonic() - start) * 1000, error=message)
            print(f'{sequence} slave={slave} {operation} ERROR {message}', flush=True)
            return False, None
        self.counts['successes'] += 1
        self.emit('api_result', sequence=sequence, slave=slave, operation=operation,
                  latency_ms=(time.monotonic() - start) * 1000, value=converted)
        print(f'{sequence} slave={slave} {operation} OK', flush=True)
        return True, value


async def diagnose(sdk, args, output, identity):
    recorder = Recorder(output / 'events.jsonl')
    before = interface_state(args.interface)
    recorder.emit('environment', identity=identity, interface_before=before,
                  options={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()})
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    attempted_open = False
    exit_code = 0
    started = time.monotonic()
    try:
        attempted_open = True
        sdk.init_socketcan_canfd(args.interface)
        recorder.emit('opened', interface=args.interface)
        client = sdk.init_device_handler(sdk.StarkProtocolType.CanFd, master_id=args.master)
        ready = {}
        for slave in args.slaves:
            if stop.is_set():
                break
            ok, info = await recorder.call(slave, 'get_device_info',
                lambda slave=slave: client.get_device_info(slave), info_values)
            ready[slave] = ok
            if ok:
                recorder.emit('context', slave=slave,
                              uses_revo2_motor_api=bool(info.uses_revo2_motor_api()))
        if args.action != 'monitor' and not stop.is_set():
            for slave in args.slaves:
                if stop.is_set():
                    break
                if not ready.get(slave, False):
                    recorder.emit('motion_skipped', slave=slave, reason='Device information failed')
                    exit_code = 1
                    continue
                if not client.uses_revo2_motor_api(slave):
                    recorder.emit('motion_skipped', slave=slave, reason='Not a Revo2 motor API device')
                    exit_code = 1
                    continue
                positions = POSES[args.action]
                # One application call only. Firmware/SDK ACK behavior is left visible.
                ok, _ = await recorder.call(slave, 'set_finger_positions',
                    lambda slave=slave: client.set_finger_positions(slave, positions), lambda value: None)
                recorder.emit('motion_command', slave=slave, action=args.action,
                              positions_sdk=positions, sdk_call_returned_success=ok)
        deadline = time.monotonic() + args.duration
        while not stop.is_set() and time.monotonic() < deadline:
            scan_start = time.monotonic()
            for slave in args.slaves:
                if stop.is_set():
                    break
                recorder.emit('status_context', slave=slave, identity_initialized=ready.get(slave, False))
                await recorder.call(slave, 'get_motor_status',
                    lambda slave=slave: client.get_motor_status(slave), motor_values)
            delay = max(0, min(deadline - time.monotonic(), 1 / args.hz - (time.monotonic() - scan_start)))
            if delay > 0:
                try:
                    await asyncio.wait_for(stop.wait(), delay)
                except asyncio.TimeoutError:
                    pass
        if stop.is_set():
            recorder.emit('interrupted')
            exit_code = 130
    except Exception as error:
        recorder.emit('fatal_error', error=f'{type(error).__name__}: {error}')
        print(str(error), file=sys.stderr)
        exit_code = 2
    finally:
        if attempted_open:
            try:
                sdk.close_socketcan()
                recorder.emit('closed')
            except Exception as error:
                recorder.emit('close_error', error=str(error))
                exit_code = 2
        if exit_code == 0 and recorder.counts['failures']:
            exit_code = 1
        summary = dict(exit_code=exit_code, counts=dict(recorder.counts), errors=dict(recorder.errors),
                       elapsed_seconds=time.monotonic() - started, interface_before=before,
                       interface_after=interface_state(args.interface), identity=identity)
        recorder.emit('summary', **summary)
        recorder.handle.close()
        (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=True, indent=2) + '\n')
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)
        print(f'Results: {output.resolve()}', flush=True)
    return exit_code


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', default='can0')
    parser.add_argument('--slaves', default='126,127')
    parser.add_argument('--master', type=int, default=1)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--hz', type=float, default=10, help='Full status scans per second, without catch-up bursts')
    parser.add_argument('--action', choices=('monitor', 'open', 'close'), default='monitor')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--info-only', action='store_true', help='Print SDK identity without opening CAN')
    parser.add_argument('--dry-run', action='store_true', help='Print API plan without importing the SDK or opening CAN')
    args = parser.parse_args(argv)
    try:
        args.slaves = [int(value) for value in args.slaves.split(',')]
    except ValueError:
        parser.error('--slaves must contain comma-separated decimal IDs')
    if not args.slaves or any(s not in (126, 127) for s in args.slaves) or len(set(args.slaves)) != len(args.slaves):
        parser.error('--slaves must be 126, 127, or 126,127 without duplicates')
    if not 1 <= args.master <= 255:
        parser.error('--master must be in 1..255')
    if not (0 < args.duration <= 600 and 0 < args.hz <= 100):
        parser.error('Require duration in (0,600] and hz in (0,100]')
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.dry_run:
        print(json.dumps(dict(interface=args.interface, slaves=args.slaves, master=args.master,
            initial_api='get_device_info (SN, firmware, hand type)',
            status_api='get_motor_status (24 registers per hand per scan)',
            action=args.action, positions_sdk=POSES.get(args.action), duration=args.duration, hz=args.hz)))
        return 0
    try:
        from bc_stark_sdk import main_mod as sdk
        identity = sdk_identity(sdk)
        if args.info_only:
            print(json.dumps(identity, indent=2))
            return 0
        if sys.platform != 'linux':
            raise RuntimeError('Live transport requires Linux SocketCAN; use --info-only or --dry-run here')
        for name in ('init_socketcan_canfd', 'close_socketcan', 'init_device_handler', 'init_logging'):
            if not hasattr(sdk, name):
                raise RuntimeError(f'Installed SDK does not expose {name}')
    except Exception as error:
        print(f'Cannot initialize SDK: {type(error).__name__}: {error}', file=sys.stderr)
        return 2
    output = args.output or Path('canfd-sdk-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    try:
        output.mkdir(parents=True, exist_ok=False)
        logging.basicConfig(level=logging.DEBUG)
        # A single argument supports existing SDK versions with this logging API.
        sdk.init_logging(sdk.LogLevel.Debug)
        (output / 'environment.json').write_text(json.dumps(identity, indent=2) + '\n')
        print(f'SDK {identity["sdk_version"]}: {identity["native_module_path"]}', flush=True)
        print(f'Results: {output.resolve()}', flush=True)
        return asyncio.run(diagnose(sdk, args, output, identity))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
