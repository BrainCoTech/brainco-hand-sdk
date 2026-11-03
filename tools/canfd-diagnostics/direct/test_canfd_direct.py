import json
import re
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

import canfd_direct as direct


def reply(slave, function, data):
    body = bytes([slave, function]) + data
    payload = body + struct.pack('<H', direct.crc16(body))
    return direct.pack_frame((slave << 16) | (1 << 8) | len(payload), payload)


class ProtocolTests(unittest.TestCase):
    def test_frame_reference_matches_requests_and_crc(self):
        text = Path(__file__).with_name('frame_reference.txt').read_text()
        sections = re.findall(
            r'slave=(\d+) (?:operation|action)=(\w+)[^\n]*\n'
            r'  TX ID=([0-9A-F]+) logical=(\d+) physical=(\d+)\n'
            r'  TX data=([0-9A-F ]+)\n'
            r'  (?:RX example ID=([0-9A-F]+) logical=\d+ physical=(\d+)\n'
            r'  RX example data=|Expected ACK ID=([0-9A-F]+) data=)([0-9A-F ]+)', text)
        self.assertEqual(len(sections), 14)
        for slave, label, tx_id, logical, physical, tx_data, rx_id, rx_size, ack_id, rx_data in sections:
            with self.subTest(slave=slave, label=label):
                planned = {name: (identifier, request) for _, name, identifier, request in
                           direct.planned_requests([int(slave)], 1, 12, 'monitor')}
                if label in direct.POSES:
                    identifier, request = direct.motion_request(int(slave), 1, label)
                else:
                    identifier, request = planned[label]
                self.assertEqual(int(tx_id, 16), identifier)
                self.assertEqual(int(logical), len(request))
                packet = direct.pack_frame(identifier, request)
                self.assertEqual(int(physical), direct.FD_FRAME.unpack(packet)[1])
                self.assertEqual(bytes.fromhex(tx_data), packet[8:8 + int(physical)])
                data = bytes.fromhex(rx_data)
                if rx_size:
                    self.assertEqual(len(data), int(rx_size))
                report = direct.inspect_response(identifier, request,
                    direct.pack_frame(int(rx_id or ack_id, 16), data))
                self.assertTrue(report['matches_request'])
                self.assertTrue(report['crc_ok'])

    def test_independent_crc_vector(self):
        self.assertEqual(direct.crc16(b'123456789'), 0x4B37)

    def test_known_read_request(self):
        identifier, request = direct.make_request(127, 1, 4, 2000, 12)
        self.assertEqual(identifier, 0x7F0108)
        self.assertEqual(request.hex(), '7f0407d0000cfa9c')

    def test_known_sn_request(self):
        self.assertEqual(direct.make_request(127, 1, 4, 3010, 10)[1].hex(), '7f040bc2000ad9cb')

    def test_corrupted_synthetic_sn(self):
        identifier, request = direct.make_request(127, 1, 4, 3010, 10)
        packet = bytearray(reply(127, 4, b'\x14' + b'EXAMPLE-SN'.ljust(20, b'\0')))
        packet[8 + 3] ^= 1
        report = direct.inspect_response(identifier, request, bytes(packet))
        self.assertTrue(report['matches_request'])
        self.assertFalse(report['crc_ok'])

    def test_padding_is_excluded(self):
        packet = bytearray(reply(127, 4, b'\x14' + b'EXAMPLE-SN'.ljust(20, b'\0')))
        packet[8 + 25:8 + 32] = b'\xAA' * 7
        report = direct.unpack_frame(bytes(packet))
        self.assertTrue(report['crc_ok'])
        self.assertTrue(report['padding_nonzero'])

    def test_wrong_device_and_master(self):
        identifier, request = direct.make_request(127, 1, 4, 2000, 1)
        for raw_id in [0x7E0107, 0x7F0207]:
            packet = direct.pack_frame(raw_id, bytes.fromhex('7f04020000d18e'))
            self.assertFalse(direct.inspect_response(identifier, request, packet)['matches_request'])

    def test_truncated_frame_does_not_raise(self):
        identifier, request = direct.make_request(127, 1, 4, 2000, 12)
        report = direct.inspect_response(identifier, request, direct.pack_frame(0x7F011D, b'\x7f\x04\x18\x00\x00\x00'))
        self.assertIn('format_error', report)
        self.assertNotIn('crc_ok', report)

    def test_wrong_byte_count_is_not_accepted(self):
        identifier, request = direct.make_request(127, 1, 4, 2000, 2)
        body = bytes([127, 4, 2, 0, 0, 0, 0])
        data = body + struct.pack('<H', direct.crc16(body))
        report = direct.inspect_response(identifier, request, direct.pack_frame(0x7F0109, data))
        self.assertFalse(report['matches_request'])

    def test_exception_is_distinct_from_crc_error(self):
        identifier, request = direct.make_request(127, 1, 4, 2000, 1)
        report = direct.inspect_response(identifier, request, reply(127, 0x84, b'\x02'))
        self.assertEqual(report['exception_code'], 2)
        self.assertTrue(report['crc_ok'])

    def test_fd_layout_and_padding(self):
        identifier, request = direct.motion_request(126, 1, 'close')
        packet = direct.pack_frame(identifier, request)
        raw_id, length, flags, _, _, data = direct.FD_FRAME.unpack(packet)
        self.assertEqual(len(packet), 72)
        self.assertEqual(raw_id, 0x807E010F)
        self.assertEqual(length, 16)
        self.assertEqual(flags, 1)
        self.assertEqual(request[2:13].hex(), '042e000306323264646464')
        self.assertEqual(data[15], 0)

    def test_write_ack_matching(self):
        identifier, request = direct.motion_request(127, 1, 'open')
        data = request[:6] + struct.pack('<H', direct.crc16(request[:6]))
        result = direct.inspect_response(identifier, request, direct.pack_frame(0x7F0108, data))
        self.assertTrue(result['matches_request'])
        self.assertTrue(result['crc_ok'])
        changed = bytearray(data)
        changed[3] ^= 1
        changed[-2:] = struct.pack('<H', direct.crc16(changed[:-2]))
        result = direct.inspect_response(identifier, request, direct.pack_frame(0x7F0108, changed))
        self.assertFalse(result['matches_request'])

    def test_controller_error_frame_is_preserved(self):
        data = struct.pack('=IB3x8s', direct.ERR | 4, 8, bytes([0, 0, 0, 0, 0, 0, 2, 3]))
        report = direct.unpack_frame(data)
        self.assertTrue(report['error_frame'])
        self.assertFalse(report['fd'])
        self.assertEqual(report['data_hex'], '00 00 00 00 00 00 02 03')

    def test_slot_and_slave_validation(self):
        self.assertEqual(len(list(direct.planned_requests([126, 127], 1, 12, 'monitor'))), 10)
        self.assertTrue(all(request[1] in (3, 4) for _, _, _, request in direct.planned_requests([126, 127], 1, 24, 'monitor')))

    def test_signed_status_decoding_and_sku(self):
        result = direct.decode_values('status_2012', [0xFFFF, 0x8000, 1, 2, 3, 4, 0, 1, 2, 3, 4, 5])
        self.assertEqual(result['currents_raw'][:2], [-1, -32768])
        self.assertEqual(result['motor_states_raw'], [0, 1, 2, 3, 4, 5])
        self.assertEqual(direct.decode_values('sku', [2])['hand'], 'left')
        self.assertEqual(direct.decode_values('sku', [1])['hand'], 'right')

    def test_timeout_then_recovery_over_real_datagram_sockets(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        with tempfile.TemporaryDirectory() as directory:
            recorder = direct.Recorder(Path(directory) / 'frames.jsonl')
            transport = direct.Transport(left, recorder, 0.05)
            identifier, request = direct.make_request(127, 1, 4, 2000, 1)
            try:
                self.assertIsNone(transport.transact('status_2000', identifier, request))
                right.recv(72)
                def respond():
                    right.recv(72)
                    right.send(reply(127, 4, b'\x02\x00\x7b'))
                worker = threading.Thread(target=respond)
                worker.start()
                result = transport.transact('status_2000', identifier, request)
                worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertEqual(result['registers_u16'], [123])
                self.assertEqual(dict(transport.counts), {'tx': 2, 'timeout': 1, 'rx': 1, 'ok': 1})
            finally:
                left.close()
                right.close()
                recorder.handle.close()
            rows = [json.loads(line) for line in (Path(directory) / 'frames.jsonl').read_text().splitlines()]
            self.assertEqual(sum(row['event'] == 'tx' for row in rows), 2)


if __name__ == '__main__':
    unittest.main()
