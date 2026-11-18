"""Exercise Windows CAN FD receive logic without loading a vendor DLL."""

import ctypes
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


class WindowsCanFdReceiveTests(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        utils = ModuleType("canfd_utils")
        utils.logger = Mock()
        self.utils = utils
        vendor = ModuleType("dll.zlgcan.zlgcan")
        vendor.ZCAN = Mock(return_value=self.driver)
        vendor.ZCAN_ReceiveFD_Data = object
        vendor.ZCAN_TYPE_CANFD = 1
        vendor.c_int = ctypes.c_int
        path = (Path(__file__).resolve().parents[1]
                / "python/revo2_canfd/zlg_win.py")
        spec = importlib.util.spec_from_file_location("zlg_win_under_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"canfd_utils": utils,
                                      "dll.zlgcan.zlgcan": vendor}), \
                patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.module)
        self.module.chn_handles = [123]
        self.clock = Clock()
        self.module.time = self.clock

    @staticmethod
    def message(can_id, flags=0):
        return SimpleNamespace(frame=SimpleNamespace(
            can_id=can_id, flags=flags, len=3, data=[1, 2, 3, 99]))

    def test_filters_echo_and_other_devices_then_strips_extended_flag(self):
        self.driver.GetReceiveNum.return_value = 4
        self.driver.ReceiveFD.return_value = ([
            self.message(0x007e0108, 0x20),
            self.message(0x007f0108),
            self.message(0x007e0208),
            self.message(0x807e0107),
        ], 4)
        self.assertEqual(self.module.zlgcan_receive_canfd_filtered(0x007e0108),
                         (0x007e0107, [1, 2, 3], 1))

    def test_empty_queue_times_out_with_backoff(self):
        self.driver.GetReceiveNum.return_value = 0
        self.assertIsNone(self.module.zlgcan_receive_canfd_filtered(
            0x007e0108, timeout_ms=3))
        self.assertEqual(self.clock.sleeps, [0.001] * 3)
        self.driver.ReceiveFD.assert_not_called()

    def test_driver_exceptions_back_off_until_deadline(self):
        for method in ["GetReceiveNum", "ReceiveFD"]:
            with self.subTest(method=method):
                self.driver.reset_mock(side_effect=True)
                self.clock = Clock()
                self.module.time = self.clock
                self.driver.GetReceiveNum.return_value = 1
                getattr(self.driver, method).side_effect = RuntimeError("disconnected")
                self.assertIsNone(self.module.zlgcan_receive_canfd_filtered(
                    0x007e0108, timeout_ms=3))
                self.assertEqual(self.clock.sleeps, [0.001] * 3)

    def test_missing_channel_does_not_call_driver(self):
        self.module.chn_handles = []
        self.assertIsNone(self.module.zlgcan_receive_canfd_filtered(0x007e0108))
        self.driver.GetReceiveNum.assert_not_called()

    def test_windows_example_callbacks_read_filtered_frames(self):
        self.utils.libstark = Mock()
        self.utils.setup_shutdown_event = Mock()
        self.utils.display_pressure_touch_status = Mock()
        self.utils.setup_pressure_touch_sensors = Mock()
        modules = {"zlg_win": self.module, "canfd_utils": self.utils}
        self.driver.GetReceiveNum.return_value = 1
        self.driver.ReceiveFD.return_value = ([self.message(0x807e0107)], 1)
        with patch.dict(sys.modules, modules), patch("platform.system", return_value="Windows"):
            for name in ("zlg_canfd", "zlg_canfd_touch_pressure"):
                with self.subTest(example=name):
                    path = Path(self.module.__file__).with_name(name + ".py")
                    spec = importlib.util.spec_from_file_location(name, path)
                    example = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(example)
                    expected = (0x007e0107, bytes([1, 2, 3]))
                    self.assertEqual(example.canfd_read(126, 0x007e0108, 1), expected)
                    if name == "zlg_canfd":
                        controller = example.Revo2CanfdController()
                        self.assertEqual(controller._canfd_read(126, 0x007e0108, 1), expected)


if __name__ == "__main__":
    unittest.main()
