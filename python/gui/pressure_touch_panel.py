"""Pressure Touch Sensor Panel - Dispatcher for all touch sensor types

Supports:
- Revo2 Pressure Touch: Distributed pressure arrays
- Revo2 Force Touch (ArrayPressure): 3D force + torque

This file acts as a dispatcher, delegating to the appropriate sub-panel
based on the connected device's hardware type.
"""

from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, QTimer

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

from .i18n import tr
from .touch_common import run_async, logger


class PressureTouchPanel(QWidget):
    """Touch Sensor Panel - auto-dispatches to the correct sub-panel.

    Uses SharedDataManager for device state.
    """

    # Mode constants
    MODE_NONE = 'none'
    MODE_PRESSURE = 'pressure'        # Pressure arrays
    MODE_FORCE = 'force'              # ArrayPressure force/torque

    def __init__(self):
        super().__init__()
        self.shared_data: Optional['SharedDataManager'] = None
        self.mode = self.MODE_NONE
        self.sub_panel: Optional[QWidget] = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(8, 8, 8, 8)

        self.ui_setup_done = False

        # Control bar (persistent across mode switches)
        self.control_layout = QHBoxLayout()
        self.control_layout.setSpacing(8)
        self.main_layout.addLayout(self.control_layout)

        # Sub-panel container
        self.panel_container = QVBoxLayout()
        self.main_layout.addLayout(self.panel_container, 1)

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_data_from_shared)
        self.update_timer.setInterval(50)

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    @property
    def device_info(self):
        return self.shared_data.device_info if self.shared_data else None

    def _clear_controls(self):
        while self.control_layout.count():
            item = self.control_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _clear_panel(self):
        if self.sub_panel:
            self.panel_container.removeWidget(self.sub_panel)
            self.sub_panel.deleteLater()
            self.sub_panel = None

    def _setup_controls(self):
        """Build control bar based on current mode"""
        self._clear_controls()

        # Enable button
        self.enable_btn = QPushButton(tr("btn_enable_touch"))
        self.enable_btn.clicked.connect(self._enable_touch)
        self.control_layout.addWidget(self.enable_btn)

        # Calibrate (Revo2 pressure only)
        if self.mode == self.MODE_PRESSURE:
            self.calibrate_btn = QPushButton(tr("btn_calibrate"))
            self.calibrate_btn.clicked.connect(self._calibrate)
            self.control_layout.addWidget(self.calibrate_btn)

        # Reset
        self.reset_btn = QPushButton(tr("btn_reset"))
        self.reset_btn.clicked.connect(self._reset)
        self.control_layout.addWidget(self.reset_btn)

        # Clear
        self.clear_btn = QPushButton(tr("btn_clear"))
        self.clear_btn.clicked.connect(self._clear_charts)
        self.control_layout.addWidget(self.clear_btn)

        self.control_layout.addStretch()

    def _setup_sub_panel(self):
        """Create and install the mode-specific sub-panel"""
        self._clear_panel()

        if self.mode == self.MODE_PRESSURE:
            from .touch_panel_pressure import PressureTouchSubPanel
            self.sub_panel = PressureTouchSubPanel()
        elif self.mode == self.MODE_FORCE:
            from .touch_panel_force import ForceTouchSubPanel
            self.sub_panel = ForceTouchSubPanel()
        else:
            return

        self.panel_container.addWidget(self.sub_panel, 1)
        self._setup_controls()
        self.ui_setup_done = True

    def update_texts(self):
        """Update texts for i18n"""
        if not self.ui_setup_done:
            return
        if hasattr(self, 'enable_btn'):
            self.enable_btn.setText(tr("btn_enable_touch"))
        if hasattr(self, 'calibrate_btn'):
            self.calibrate_btn.setText(tr("btn_calibrate"))
        if hasattr(self, 'reset_btn'):
            self.reset_btn.setText(tr("btn_reset"))
        if hasattr(self, 'clear_btn'):
            self.clear_btn.setText(tr("btn_clear"))

    def set_device(self, device, slave_id, device_info, shared_data=None):
        """Set device and auto-detect touch sensor mode"""
        if self.shared_data:
            try:
                self.shared_data.pressure_touch_updated.disconnect(self._on_pressure_touch_updated)
            except Exception:
                pass

        self.shared_data = shared_data

        if not device:
            self.update_timer.stop()
            return

        # Determine mode from hardware type
        from common_imports import uses_pressure_touch_api, sdk

        old_mode = self.mode
        if device_info and hasattr(device_info, 'hardware_type'):
            hw_type = device_info.hardware_type

            if sdk and hw_type == sdk.StarkHardwareType.Revo2TouchArrayPressure:
                self.mode = self.MODE_FORCE
            elif uses_pressure_touch_api(hw_type):
                self.mode = self.MODE_PRESSURE
            else:
                self.mode = self.MODE_NONE
                self.setEnabled(False)
                return
        else:
            self.mode = self.MODE_NONE
            self.setEnabled(False)
            return

        # Rebuild UI if mode changed
        if self.mode != old_mode or not self.ui_setup_done:
            self._setup_sub_panel()

        self.setEnabled(True)

        # Connect signals
        if self.mode == self.MODE_PRESSURE and shared_data:
            if hasattr(shared_data, 'pressure_touch_updated'):
                shared_data.pressure_touch_updated.connect(self._on_pressure_touch_updated)

        self.update_timer.start()

    def clear_device(self):
        """Clear device when disconnected"""
        self.update_timer.stop()
        if self.shared_data:
            try:
                self.shared_data.pressure_touch_updated.disconnect(self._on_pressure_touch_updated)
            except Exception:
                pass
        self.shared_data = None

    # =========================================================================
    # Data update callbacks
    # =========================================================================

    def _on_pressure_touch_updated(self, summary_data, detailed_data):
        """Handle pressure touch data signal (Revo2 Pressure mode)"""
        if self.mode == self.MODE_PRESSURE and self.sub_panel:
            self.sub_panel.update_summary(summary_data)
            self.sub_panel.update_detail(detailed_data)

    def _update_data_from_shared(self):
        """Timer callback - read from shared data buffers"""
        if not self.device or not self.sub_panel:
            return

        if self.mode == self.MODE_FORCE:
            # Force: read from array_pressure or force3d touch buffer
            buf = None
            if self.shared_data:
                buf = getattr(self.shared_data, 'array_pressure_touch_buffer', None) or \
                      getattr(self.shared_data, 'force3d_touch_buffer', None)
            if buf:
                try:
                    data_list = buf.pop_all()
                    if data_list:
                        for data in data_list[-5:]:
                            if data and hasattr(data, 'data'):
                                self.sub_panel.update_data(list(data.data))
                except Exception:
                    pass

    # =========================================================================
    # Button handlers
    # =========================================================================

    def _clear_charts(self):
        if self.sub_panel:
            self.sub_panel.clear()

    def _enable_touch(self):
        if self.device:
            logger.info(f"[TouchPanel] Enable touch sensors (mode={self.mode})")
            run_async(self._async_enable_touch())

    async def _async_enable_touch(self):
        if not self.device:
            return
        try:
            await self.device.touch_sensor_setup(self.slave_id, 0x1F)
            logger.info("[TouchPanel] Enable completed")
        except Exception as e:
            logger.warn(f"[TouchPanel] Enable failed: {e}")

    def _calibrate(self):
        if self.device and self.mode == self.MODE_PRESSURE:
            run_async(self._async_calibrate())

    async def _async_calibrate(self):
        if not self.device:
            return
        try:
            await self.device.touch_sensor_calibrate(self.slave_id, 0x1F)
            logger.info("[TouchPanel] Calibrate completed")
        except Exception as e:
            logger.warn(f"[TouchPanel] Calibrate failed: {e}")

    def _reset(self):
        if self.device:
            run_async(self._async_reset())
            self._clear_charts()

    async def _async_reset(self):
        if not self.device:
            return
        try:
            await self.device.touch_sensor_reset(self.slave_id, 0x1F)
            logger.info("[TouchPanel] Reset completed")
        except Exception as e:
            logger.warn(f"[TouchPanel] Reset failed: {e}")
