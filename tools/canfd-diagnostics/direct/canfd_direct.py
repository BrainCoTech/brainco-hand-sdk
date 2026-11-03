#!/usr/bin/env python3
"""Revo2 CAN FD diagnostics using only Python's standard library and SocketCAN."""
import argparse
import collections
import datetime
import hashlib
import json
import platform
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

EFF = 0x80000000
RTR = 0x40000000
ERR = 0x20000000
MASK = 0x1FFFFFFF
FD_FRAME = struct.Struct('=IBBBB64s')
FD_LENGTHS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)
POSES = {'open': [0, 0, 0, 0, 0, 0], 'close': [50, 50, 100, 100, 100, 100]}


def crc16(data):
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value


def make_request(slave, master, function, address, values_or_count):
    if function in (3, 4):
        count = values_or_count
        if not 1 <= count <= 29:
            raise ValueError('Read count must be in 1..29')
        body = struct.pack('>BBHH', slave, function, address, count)
    elif function == 16:
        values = values_or_count
        count = len(values)
        if not 1 <= count <= 27:
            raise ValueError('Write count must be in 1..27')
        body = struct.pack('>BBHHB', slave, function, address, count, count * 2)
        body += struct.pack('>' + 'H' * count, *values)
    else:
        raise ValueError('Unsupported request function')
    payload = body + struct.pack('<H', crc16(body))
    identifier = (slave << 16) | (master << 8) | len(payload)
    return identifier, payload


def motion_request(slave, master, action):
    positions = POSES[action]
    words = [positions[i] | (positions[i + 1] << 8) for i in (0, 2, 4)]
    return make_request(slave, master, 16, 1070, words)


def pack_frame(identifier, payload):
    length = next(length for length in FD_LENGTHS if length >= len(payload))
    wire = payload.ljust(length, b'\0')
    return FD_FRAME.pack(identifier | EFF, length, 1, 0, 0, wire)


def unpack_frame(packet):
    if len(packet) == 16:
        raw_id, length, storage = struct.unpack("=IB3x8s", packet)
        return {"can_id": f"{raw_id & MASK:08X}", "fd": False,
                "extended": bool(raw_id & EFF), "error_frame": bool(raw_id & ERR),
                "remote_frame": bool(raw_id & RTR), "physical_length": length,
                "data_hex": storage[:min(length, 8)].hex(" "), "socket_bytes_hex": packet.hex(" "),
                "format_error": "Classical CAN or controller error frame"}
    if len(packet) != FD_FRAME.size:
        return {'transport_error': 'Not a CAN FD frame', 'socket_bytes_hex': packet.hex(' ')}
    raw_id, length, flags, _, _, storage = FD_FRAME.unpack(packet)
    if length > 64:
        return {'transport_error': 'CAN FD length exceeds 64', 'socket_bytes_hex': packet.hex(' ')}
    identifier = raw_id & MASK
    data = storage[:length]
    logical = identifier & 255
    report = {'can_id': f'{identifier:08X}', 'extended': bool(raw_id & EFF),
              'error_frame': bool(raw_id & ERR), 'remote_frame': bool(raw_id & RTR),
              'fd': True, 'brs': bool(flags & 1), 'esi': bool(flags & 2), 'flags': flags,
              'physical_length': length, 'logical_length_from_id': logical,
              'data_hex': data.hex(' '), 'socket_bytes_hex': packet.hex(' ')}
    if not 4 <= logical <= length:
        report['format_error'] = 'Logical length is outside received data'
        return report
    body = data[:logical - 2]
    stored = int.from_bytes(data[logical - 2:logical], 'little')
    calculated = crc16(body)
    report.update(crc_stored=f'{stored:04X}', crc_calculated=f'{calculated:04X}',
                  crc_ok=stored == calculated, padding_hex=data[logical:].hex(' '),
                  padding_nonzero=any(data[logical:]))
    return report


def inspect_response(request_id, request, packet):
    report = unpack_frame(packet)
    report['matches_request'] = False
    if 'transport_error' in report:
        return report
    if not report['fd'] or report['error_frame'] or report['remote_frame'] or not report['extended']:
        report['mismatch'] = 'Error, remote or standard frame'
        return report
    if int(report['can_id'], 16) >> 8 != request_id >> 8:
        report['mismatch'] = 'Different device or master ID'
        return report
    data = bytes.fromhex(report['data_hex'])
    if len(data) < 2 or data[0] != request[0]:
        report['mismatch'] = 'Invalid slave byte'
        return report
    if data[1] == (request[1] | 0x80):
        report.update(matches_request=True, exception_code=data[2] if len(data) >= 3 else None)
        if report['logical_length_from_id'] != 5:
            report['format_error'] = 'Exception response must have logical length 5'
        return report
    if data[1] != request[1]:
        report['mismatch'] = 'Different function code'
        return report
    count = int.from_bytes(request[4:6], 'big')
    logical = 5 + 2 * count if request[1] in (3, 4) else 8
    report['expected_logical_length'] = logical
    if report['logical_length_from_id'] != logical or len(data) < logical:
        report['format_error'] = 'Unexpected response length'
        report['matches_request'] = True
        return report
    if request[1] in (3, 4):
        if data[2] != 2 * count:
            report['mismatch'] = 'Unexpected byte count'
            return report
        report['registers_u16'] = list(struct.unpack('>' + 'H' * count, data[3:3 + count * 2]))
    elif data[:6] != request[:6]:
        report['mismatch'] = 'Write echo does not match request'
        return report
    report['matches_request'] = True
    return report


def decode_values(label, values):
    if label in ('sn', 'firmware'):
        raw = struct.pack('>' + 'H' * len(values), *values)
        return {'text': raw.rstrip(b'\0').decode('ascii', errors='backslashreplace')}
    if label == 'sku':
        return {'sku': values[0], 'hand': {1: 'right', 2: 'left', 3: 'right', 4: 'left'}.get(values[0], 'unknown')}
    address = int(label.split('_')[1])
    result = {}
    for base, name in [(2000, 'positions_raw'), (2006, 'speeds_raw'),
                       (2012, 'currents_raw'), (2018, 'motor_states_raw')]:
        offset = base - address
        if 0 <= offset and offset + 6 <= len(values):
            data = values[offset:offset + 6]
            if base in (2006, 2012):
                data = [value if value < 0x8000 else value - 0x10000 for value in data]
            result[name] = data
    return result


class Recorder:
    def __init__(self, path):
        self.handle = path.open('x', encoding='utf-8')

    def emit(self, event, **fields):
        record = dict(event=event, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      monotonic_ns=time.monotonic_ns(), **fields)
        self.handle.write(json.dumps(record, ensure_ascii=True) + '\n')
        self.handle.flush()
        return record


def interface_state(interface):
    try:
        process = subprocess.run(['ip', '-details', '-statistics', 'link', 'show', 'dev', interface],
                                 capture_output=True, text=True, timeout=5)
        return dict(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': str(error)}


class Transport:
    def __init__(self, sock, recorder, timeout):
        self.sock, self.recorder, self.timeout = sock, recorder, timeout
        self.sequence = 0
        self.counts = collections.Counter()

    def transact(self, label, identifier, request):
        self.sequence += 1
        sequence = self.sequence
        # Keep queued frames visible rather than silently assigning them to a new request.
        for _ in range(256):
            if not select.select([self.sock], [], [], 0)[0]:
                break
            self.recorder.emit('orphan_rx', sequence=sequence,
                               **unpack_frame(self.sock.recv(72)))
        else:
            raise RuntimeError('Receive queue remains busy; stop other transmitters first')
        packet = pack_frame(identifier, request)
        self.sock.settimeout(self.timeout)
        sent = self.sock.send(packet)
        if sent != len(packet):
            raise OSError('Incomplete CAN FD send')
        started = time.monotonic()
        self.recorder.emit('tx', sequence=sequence, label=label,
                           request_hex=request.hex(' '), **unpack_frame(packet))
        self.counts['tx'] += 1
        deadline = started + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.sock], [], [], max(0, remaining))[0]:
                self.counts['timeout'] += 1
                self.recorder.emit('timeout', sequence=sequence, label=label)
                print(f'{sequence} {label} timeout', flush=True)
                return None
            packet = self.sock.recv(72)
            report = inspect_response(identifier, request, packet)
            self.recorder.emit('rx', sequence=sequence, label=label, **report)
            self.counts['rx'] += 1
            if report.get('error_frame'):
                self.counts['controller_error_frames'] += 1
            if not report['matches_request']:
                self.counts['unmatched_rx'] += 1
                continue
            valid = (report.get('crc_ok') is True and not report.get('format_error')
                     and 'exception_code' not in report)
            self.counts['ok' if valid else 'invalid_response'] += 1
            self.recorder.emit('result', sequence=sequence, label=label, ok=valid,
                               latency_ms=(time.monotonic() - started) * 1000)
            print(f'{sequence} {label} {"OK" if valid else "INVALID"} '
                  f'CRC={report.get("crc_stored")}/{report.get("crc_calculated")}', flush=True)
            return report if valid else None


def status_queries(count):
    return [(2000, 24)] if count == 24 else [(2000, 12), (2012, 12)]


def planned_requests(slaves, master, count, action):
    for slave in slaves:
        for label, function, address, size in [('sn', 4, 3010, 10), ('firmware', 4, 3000, 10), ('sku', 3, 901, 1)]:
            yield slave, label, *make_request(slave, master, function, address, size)
        for address, size in status_queries(count):
            yield slave, f'status_{address}', *make_request(slave, master, 4, address, size)
        if action != 'monitor':
            yield slave, action, *motion_request(slave, master, action)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', default='can0')
    parser.add_argument('--slaves', default='126,127')
    parser.add_argument('--master', type=int, default=1)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--hz', type=float, default=10, help='Full status scans per second, without catch-up bursts')
    parser.add_argument('--timeout', type=float, default=0.2)
    parser.add_argument('--status-count', type=int, choices=(12, 24), default=12)
    parser.add_argument('--action', choices=('monitor', 'open', 'close'), default='monitor')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        args.slaves = [int(value) for value in args.slaves.split(',')]
    except ValueError:
        parser.error('--slaves must contain comma-separated decimal IDs')
    if not args.slaves or any(value not in (126, 127) for value in args.slaves) or len(set(args.slaves)) != len(args.slaves):
        parser.error('--slaves must be 126, 127, or 126,127 without duplicates')
    if not 1 <= args.master <= 255:
        parser.error('--master must be in 1..255')
    if not (0 < args.duration <= 600 and 0 < args.hz <= 100 and 0 < args.timeout <= 5):
        parser.error('Require duration in (0,600], hz in (0,100], timeout in (0,5]')
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.dry_run:
        for slave, label, identifier, request in planned_requests(args.slaves, args.master, args.status_count, args.action):
            print(json.dumps(dict(slave=slave, label=label, **unpack_frame(pack_frame(identifier, request)))))
        return 0
    if sys.platform != 'linux':
        raise RuntimeError('Live transport requires Linux SocketCAN; --dry-run is platform independent')
    output = args.output or Path('canfd-direct-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    output.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(output / 'frames.jsonl')
    sock = None
    transport = None
    exit_code = 0
    try:
        recorder.emit('environment', python=sys.version, platform=platform.platform(),
                      script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      options={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                      interface_before=interface_state(args.interface))
        sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        sock.setsockopt(socket.SOL_CAN_RAW, getattr(socket, 'CAN_RAW_FD_FRAMES', 5), 1)
        sock.setsockopt(socket.SOL_CAN_RAW, getattr(socket, 'CAN_RAW_RECV_OWN_MSGS', 4), 0)
        sock.setsockopt(socket.SOL_CAN_RAW, getattr(socket, 'CAN_RAW_ERR_FILTER', 2), struct.pack('=I', MASK))
        sock.bind((args.interface,))
        transport = Transport(sock, recorder, args.timeout)
        ready = {slave: True for slave in args.slaves}
        for slave, label, identifier, request in planned_requests(args.slaves, args.master, args.status_count, 'monitor'):
            if label.startswith('status_'):
                continue
            response = transport.transact(label, identifier, request)
            if response:
                recorder.emit('decoded', slave=slave, label=label,
                               **decode_values(label, response['registers_u16']))
            else:
                ready[slave] = False
        if args.action != 'monitor':
            for slave in args.slaves:
                if not ready[slave]:
                    recorder.emit('motion_skipped', slave=slave, reason='Identity reads failed')
                    exit_code = 1
                    continue
                identifier, request = motion_request(slave, args.master, args.action)
                response = transport.transact(args.action, identifier, request)
                if response is None:
                    exit_code = 1
                recorder.emit('motion_command', slave=slave, action=args.action,
                               positions_percent=POSES[args.action], acknowledgement_valid=response is not None)
        started = time.monotonic()
        while time.monotonic() - started < args.duration:
            scan_start = time.monotonic()
            for slave in args.slaves:
                for address, count in status_queries(args.status_count):
                    label = f'status_{address}'
                    identifier, request = make_request(slave, args.master, 4, address, count)
                    response = transport.transact(label, identifier, request)
                    if response:
                        recorder.emit('decoded', slave=slave, label=label,
                                       **decode_values(label, response['registers_u16']))
            time.sleep(max(0, 1 / args.hz - (time.monotonic() - scan_start)))
    except KeyboardInterrupt:
        recorder.emit('interrupted')
        exit_code = 130
    except Exception as error:
        recorder.emit('fatal_error', error=f'{type(error).__name__}: {error}')
        print(str(error), file=sys.stderr)
        exit_code = 2
    finally:
        if sock:
            sock.close()
        counts = dict(transport.counts) if transport else {}
        if exit_code == 0 and (counts.get('timeout', 0) or counts.get('invalid_response', 0)):
            exit_code = 1
        summary = dict(counts=counts, exit_code=exit_code, interface_after=interface_state(args.interface))
        recorder.emit('summary', **summary)
        recorder.handle.close()
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(f'Results: {output.resolve()}', flush=True)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
