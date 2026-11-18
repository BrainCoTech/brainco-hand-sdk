"""Exercise Linux CAN FD receive paths with simulated socket and vendor I/O."""

import ctypes
import importlib.util
from pathlib import Path
import socket
import struct
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


EXAMPLES = Path(__file__).resolve().parents[1] / "python"


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinuxCanFdTests(unittest.TestCase):
    def setUp(self):
        utils = ModuleType("canfd_utils")
        utils.logger = Mock()
        self.driver = Mock()
        with patch.object(ctypes.cdll, "LoadLibrary", return_value=self.driver):
            self.vendor = load_module(EXAMPLES / "dll/zlgcan/zlgcan_linux.py")
        with patch.dict(sys.modules, {"canfd_utils": utils, "common_imports": utils,
                                     "dll.zlgcan.zlgcan_linux": self.vendor}), \
                patch.object(sys, "path", sys.path.copy()):
            self.zlg = load_module(EXAMPLES / "revo2_canfd/zlg_linux.py")
            self.socketcan = load_module(EXAMPLES / "common_socketcan.py")
        self.zlg.time = Mock()
        self.socketcan.time = Mock()
        self.sock = Mock()
        self.socketcan._sock = self.sock
        self.socketcan._is_canfd = True

    def test_zlg_empty_queue_and_driver_failure(self):
        read = self.zlg.zlgcan_receive_canfd_filtered
        self.driver.VCI_GetReceiveNum.return_value = 0
        self.assertIsNone(read(0x007e0108, max_retries=2))
        self.driver.VCI_GetReceiveNum.return_value = 1
        self.driver.VCI_ReceiveFD.return_value = 0
        self.assertIsNone(read(0x007e0108, max_retries=2))
        for queued, received in [(-1, 0), (0xffffffff, 0), (1, -1), (1, 2)]:
            with self.subTest(queued=queued, received=received):
                self.driver.VCI_GetReceiveNum.return_value = queued
                self.driver.VCI_ReceiveFD.return_value = received
                with self.assertRaises(OSError):
                    read(0x007e0108, max_retries=2)

    def test_zlg_matches_after_transient_error(self):
        msg = self.vendor.ZCAN_FD_MSG()
        msg.hdr.id = 0x007e0107
        msg.hdr.len = 1
        msg.dat[0] = 42
        with patch.object(self.zlg, "canfd_receive", side_effect=[OSError("busy"), [msg]]):
            self.assertEqual(self.zlg.zlgcan_receive_canfd_filtered(0x007e0108),
                             (0x007e0107, [42], 1))

    def test_socket_timeout_and_device_failure(self):
        read = self.socketcan.socketcan_receive_canfd_filtered
        self.sock.recv.side_effect = socket.timeout()
        self.assertIsNone(read(0x007e0108))
        self.sock.recv.side_effect = OSError("link down")
        with self.assertRaisesRegex(OSError, "link down"):
            read(0x007e0108)
        frame = struct.pack(self.socketcan.CANFD_FRAME_FMT, 0x807e0107, 1, 0, 0, b"*")
        self.sock.recv.side_effect = [OSError("busy"), frame]
        self.assertEqual(read(0x007e0108), (0x007e0107, b"*", 1))
        self.socketcan._sock = None
        with self.assertRaisesRegex(RuntimeError, "not open"):
            read(0x007e0108)

    def test_socket_send_checks_frame_capacity_before_io(self):
        for mode, capacity in [(False, 8), (True, 64)]:
            with self.subTest(canfd=mode):
                self.socketcan._is_canfd = mode
                self.sock.reset_mock()
                data = bytes(range(capacity))
                self.assertTrue(self.socketcan.socketcan_send_message(0x123, data))
                frame = self.sock.send.call_args.args[0]
                self.assertEqual(frame[8:], data)
                self.assertFalse(self.socketcan.socketcan_send_message(0x123, data + b"x"))
                self.sock.send.assert_called_once()
