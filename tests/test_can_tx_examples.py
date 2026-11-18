"""Exercise the SDK example transmit callbacks with simulated adapters."""

import importlib.util
from pathlib import Path
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch


EXAMPLES = Path(__file__).resolve().parents[1] / "python"


def mock_module(name, symbols):
    module = ModuleType(name)
    for symbol in symbols.split():
        setattr(module, symbol, Mock())
    return module


class CanTransmitTests(unittest.TestCase):
    def test_adapter_send_result_reaches_each_callback(self):
        utils = mock_module(
            "can_utils",
            "logger libstark setup_shutdown_event print_finger_touch_data "
            "display_pressure_touch_status setup_pressure_touch_sensors",
        )
        zlg = mock_module(
            "zlg_linux",
            "zlgcan_open zlgcan_close zlgcan_send_message zlgcan_receive_message "
            "zlgcan_receive_canfd_filtered",
        )
        socketcan = mock_module(
            "socketcan_linux_utils",
            "socketcan_open socketcan_close socketcan_send_message "
            "socketcan_receive_message socketcan_receive_filtered",
        )
        modules = {"can_utils": utils, "canfd_utils": utils, "zlg_linux": zlg,
                   "socketcan_linux_utils": socketcan}
        cases = [
            ("revo1_can/zlg_can", "Revo1CanController", "_can_send"),
            ("revo1_can/socketcan_can", "Revo1CanController", "_can_send"),
            ("revo2_can/zlg_can", "Revo2CanController", "_can_send"),
            ("revo2_can/socketcan_can", "Revo2CanController", "_can_send"),
            ("revo2_canfd/zlg_canfd", "Revo2CanfdController", "_canfd_send"),
            ("revo2_canfd/zlg_canfd", None, "canfd_send"),
            ("revo2_canfd/zlg_canfd_touch_pressure", None, "canfd_send"),
            ("revo2_canfd/socketcan_canfd", None, "canfd_send"),
        ]
        with patch.dict(sys.modules, modules), patch("platform.system", return_value="Linux"):
            for path, controller, method in cases:
                with self.subTest(path=path, method=method):
                    spec = importlib.util.spec_from_file_location("example", EXAMPLES / (path + ".py"))
                    example = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(example)
                    owner = getattr(example, controller)() if controller else example
                    send = getattr(owner, method)
                    driver = (zlg.zlgcan_send_message if "zlg_" in path
                              else socketcan.socketcan_send_message)
                    driver.side_effect = None
                    driver.return_value = False
                    with self.assertRaisesRegex(RuntimeError, "0x123"):
                        send(1, 0x123, [1, 2])
                    driver.return_value = True
                    self.assertIs(send(1, 0x123, [1, 2]), True if controller else None)
                    driver.assert_called_with(0x123, bytes([1, 2]))
                    driver.side_effect = OSError("adapter disconnected")
                    with self.assertRaisesRegex(OSError, "adapter disconnected"):
                        send(1, 0x123, [1, 2])
