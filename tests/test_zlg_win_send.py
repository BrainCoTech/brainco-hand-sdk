"""Verify classic CAN frame lengths without opening a Windows adapter."""

import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class WindowsClassicCanTests(unittest.TestCase):
    def test_send_preserves_eight_bytes_and_rejects_nine(self):
        examples = Path(__file__).resolve().parents[1] / "python"
        driver = Mock()
        driver.Transmit.return_value = 1
        with patch.object(sys, "path", [str(examples), *sys.path]), patch.dict(sys.modules):
            vendor = importlib.import_module("dll.zlgcan.zlgcan")
            with patch.object(vendor, "ZCAN", return_value=driver):
                adapter = importlib.import_module("dll.zlgcan.zlgcan_win_utils")
            adapter.chn_handles = [123]
            payload = bytes(range(8))
            self.assertTrue(adapter.zlgcan_send_message(0x123, payload))
            frame = driver.Transmit.call_args.args[1][0].frame
            self.assertEqual((frame.can_dlc, bytes(frame.data)), (8, payload))
            self.assertFalse(adapter.zlgcan_send_message(0x123, payload + b"x"))
            driver.Transmit.assert_called_once()
