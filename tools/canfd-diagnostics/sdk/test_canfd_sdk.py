import asyncio
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import canfd_sdk as diagnostic


class FakeInfo:
    serial_number = 'EXAMPLE-SN'
    firmware_version = '1.0.22.U'
    hand_type = 'Left'
    hardware_type = 'Revo2Basic'
    description = 'Example device'
    def uses_revo2_motor_api(self):
        return True


class FakeClient:
    def __init__(self, bad_identity=False, bad_status=False, revo2=True):
        self.calls = []
        self.bad_identity, self.bad_status, self.revo2 = bad_identity, bad_status, revo2
    async def get_device_info(self, slave):
        self.calls.append(('info', slave))
        if self.bad_identity:
            raise RuntimeError('crc check failed')
        return FakeInfo()
    def uses_revo2_motor_api(self, slave):
        return self.revo2
    async def get_motor_status(self, slave):
        self.calls.append(('status', slave))
        if self.bad_status:
            raise RuntimeError('status crc check failed')
        return types.SimpleNamespace(positions=[0]*6, speeds=[0]*6, currents=[0]*6, states=['Idle']*6)
    async def set_finger_positions(self, slave, positions):
        self.calls.append(('write', slave, list(positions)))


class FakeSdk:
    StarkProtocolType = types.SimpleNamespace(CanFd='CANFD')
    def __init__(self, client):
        self.client, self.opens, self.closes = client, 0, 0
    def init_socketcan_canfd(self, interface):
        self.opens += 1
    def close_socketcan(self):
        self.closes += 1
    def init_device_handler(self, protocol, master_id):
        return self.client


class DiagnosticTests(unittest.TestCase):
    def run_case(self, action='monitor', **client_options):
        client = FakeClient(**client_options)
        sdk = FakeSdk(client)
        args = diagnostic.parse_args(['--slaves','126,127','--duration','0.001','--hz','100','--action',action])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch.object(diagnostic, 'interface_state', return_value={'test': True}):
                code = asyncio.run(diagnostic.diagnose(sdk, args, output, {'test_sdk': True}))
            rows = [json.loads(line) for line in (output/'events.jsonl').read_text().splitlines()]
            summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(sdk.opens,1)
        self.assertEqual(sdk.closes,1)
        return client, code, rows, summary

    def test_default_is_read_only_and_serializes_both_slaves(self):
        client, code, rows, summary = self.run_case()
        self.assertEqual(code,0)
        self.assertFalse(any(call[0]=='write' for call in client.calls))
        self.assertEqual(client.calls[:4],[('info',126),('info',127),('status',126),('status',127)])
        self.assertEqual(summary['counts']['failures'],0)

    def test_close_maps_to_matching_direct_percent_pose_once(self):
        client, code, rows, summary = self.run_case('close')
        writes = [call for call in client.calls if call[0]=='write']
        self.assertEqual(writes,[('write',126,[500,500,1000,1000,1000,1000]),
                                 ('write',127,[500,500,1000,1000,1000,1000])])
        self.assertEqual(code,0)

    def test_open_is_zero_pose(self):
        client, code, _, _ = self.run_case('open')
        self.assertEqual([c[2] for c in client.calls if c[0]=='write'],[[0]*6,[0]*6])

    def test_bad_identity_skips_motion_but_keeps_status_attempts(self):
        client, code, rows, summary = self.run_case('close',bad_identity=True)
        self.assertEqual(code,1)
        self.assertFalse(any(c[0]=='write' for c in client.calls))
        self.assertTrue(any(c[0]=='status' for c in client.calls))
        self.assertEqual(sum(r['event']=='motion_skipped' for r in rows),2)
        self.assertEqual(summary['errors']['RuntimeError: crc check failed'],2)

    def test_unknown_motor_api_skips_motion(self):
        client, code, rows, summary = self.run_case('close',revo2=False)
        self.assertEqual(code,1)
        self.assertFalse(any(c[0]=='write' for c in client.calls))

    def test_status_errors_are_preserved_and_driver_is_closed(self):
        client, code, rows, summary = self.run_case(bad_status=True)
        self.assertEqual(code,1)
        self.assertEqual(summary['errors']['RuntimeError: status crc check failed'],2)
        self.assertTrue(any(r['event']=='closed' for r in rows))

    def test_fatal_after_open_still_closes(self):
        sdk=FakeSdk(FakeClient())
        sdk.init_device_handler=mock.Mock(side_effect=RuntimeError('init failed'))
        args=diagnostic.parse_args(['--duration','0.001'])
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(diagnostic, 'interface_state', return_value={}):
                code=asyncio.run(diagnostic.diagnose(sdk,args,Path(directory),{}))
        self.assertEqual(code,2)
        self.assertEqual(sdk.closes,1)

    def test_invalid_motor_vector_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            diagnostic.motor_values(types.SimpleNamespace(positions=[0]*5))

    def test_cli_rejects_invalid_ids_and_nonfinite_parameters(self):
        for values in [['--slaves','126,126'],['--slaves','128'],['--duration','nan'],['--hz','inf']]:
            with self.assertRaises(SystemExit):
                diagnostic.parse_args(values)

    def test_preview_does_not_import_sdk_or_send(self):
        with mock.patch.dict('sys.modules',{'bc_stark_sdk':None}):
            self.assertEqual(diagnostic.main(['--slaves','127','--dry-run']),0)


if __name__ == '__main__':
    unittest.main()
