"""DFU - Device Firmware Upgrade Panel

Runs DFU in a dedicated Qt worker thread so the GUI can stay responsive
without spawning a separate Python process.
"""

import asyncio
import inspect
import os
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .styles import COLORS

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

DfuState = sdk.DfuState

SCRIPT_DIR = Path(__file__).resolve().parent
OTA_DIR = SCRIPT_DIR.parent / "ota_bin"

DEFAULT_FIRMWARE_PATHS = {
    "revo1_basic": OTA_DIR / "modbus" / "FW_MotorController_Release_SecureOTA_0.1.7.C.ota",
    "revo1_touch": OTA_DIR / "touch" / "FW_MotorController_Release_SecureOTA_V1.8.53.F.ota",
    "revo1_advanced": OTA_DIR / "stark2" / "Revo1.8_V1.0.3.C_2602031800.bin",
    "revo2_485_canfd": OTA_DIR / "stark2" / "Revo2_V1.0.20.U_2601091030.bin",
}

DFU_STATE_NAMES = {
    0: "dfu_state_idle",
    1: "dfu_state_starting",
    2: "dfu_state_started",
    3: "dfu_state_transferring",
    4: "dfu_state_completed",
    5: "dfu_state_aborted",
}

FIRMWARE_TYPES = {
    "Revo1Basic": {"name": "Revo1 Basic", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo1_basic")},
    "Revo1Touch": {"name": "Revo1 Touch", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo1_touch")},
    "Revo1Advanced": {"name": "Revo1 Advanced", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo1_advanced")},
    "Revo1AdvancedTouch": {"name": "Revo1 Advanced Touch", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo1_advanced")},
    "Revo2Basic": {"name": "Revo2 Basic", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo2_485_canfd")},
    "Revo2Touch": {"name": "Revo2 Touch", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo2_485_canfd")},
    "Revo2TouchPressure": {"name": "Revo2 Touch Pressure", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo2_485_canfd")},
    "Revo2TouchForce3D": {"name": "Revo2 Touch Force3D", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo2_485_canfd")},
    "Revo2TouchArrayPressure": {"name": "Revo2 Touch ArrayPressure", "default_path": DEFAULT_FIRMWARE_PATHS.get("revo2_485_canfd")},
}


class DfuWorker(QObject):
    """Run DFU in a background thread and forward updates with Qt signals."""

    progress = Signal(int)
    state_changed = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, device, slave_id: int, firmware_path: str, wait_secs: int = 4):
        super().__init__()
        self.device = device
        self.slave_id = slave_id
        self.firmware_path = firmware_path
        self.wait_secs = wait_secs

    def run(self):
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_dfu(loop))
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _run_dfu(self, loop: asyncio.AbstractEventLoop):
        done_event = asyncio.Event()
        result = {"done": False, "success": False, "message": ""}

        def finish(success: bool, message: str):
            if result["done"]:
                return
            result["done"] = True
            result["success"] = success
            result["message"] = message
            if loop.is_closed():
                return
            loop.call_soon_threadsafe(done_event.set)

        def on_dfu_state(slave_id: int, state: int):
            self.state_changed.emit(state)

            try:
                dfu_state = sdk.DfuState(state)
            except Exception:
                dfu_state = None

            if dfu_state == sdk.DfuState.Completed:
                finish(True, "")
            elif dfu_state == sdk.DfuState.Aborted:
                finish(False, "DFU aborted by device")

        def on_dfu_progress(slave_id: int, progress: float):
            percent = max(0, min(100, int(progress * 100)))
            self.progress.emit(percent)

        start_result = self.device.start_dfu(
            self.slave_id,
            self.firmware_path,
            self.wait_secs,
            on_dfu_state,
            on_dfu_progress,
        )

        if asyncio.isfuture(start_result) or inspect.isawaitable(start_result):
            await start_result

        if not done_event.is_set():
            try:
                await asyncio.wait_for(done_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                finish(True, "")

        self.finished.emit(result["success"], result["message"])


class DfuPanel(QWidget):
    """DFU firmware upgrade panel."""

    dfu_started = Signal()
    dfu_finished = Signal(bool)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("BrainCo", "StarkSDK")
        self.shared_data: Optional["SharedDataManager"] = None
        self._dfu_thread: Optional[QThread] = None
        self._dfu_worker: Optional[DfuWorker] = None
        self._setup_ui()

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    @property
    def device_info(self):
        return self.shared_data.device_info if self.shared_data else None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        warning_frame = QGroupBox()
        warning_frame.setStyleSheet(
            """
            QGroupBox {
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 12px;
            }
            """
        )
        warning_layout = QVBoxLayout(warning_frame)

        self.warning_title_label = QLabel(tr("dfu_warning_title"))
        self.warning_title_label.setStyleSheet("font-weight: bold; color: #856404;")
        warning_layout.addWidget(self.warning_title_label)

        self.warning_text_label = QLabel()
        self.warning_text_label.setStyleSheet("color: #856404;")
        self.warning_text_label.setWordWrap(True)
        warning_layout.addWidget(self.warning_text_label)

        layout.addWidget(warning_frame)

        self.device_group = QGroupBox(tr("device_info"))
        device_layout = QHBoxLayout(self.device_group)

        self.device_type_label = QLabel(tr("device_type") + ": --")
        device_layout.addWidget(self.device_type_label)

        self.firmware_version_label = QLabel(tr("current_firmware") + ": --")
        device_layout.addWidget(self.firmware_version_label)

        device_layout.addStretch()
        layout.addWidget(self.device_group)

        firmware_group = QGroupBox(tr("firmware_selection"))
        firmware_layout = QVBoxLayout(firmware_group)

        type_layout = QHBoxLayout()
        self.firmware_type_label = QLabel(tr("firmware_type") + ":")
        type_layout.addWidget(self.firmware_type_label)

        self.firmware_type_combo = QComboBox()
        for key, info in FIRMWARE_TYPES.items():
            self.firmware_type_combo.addItem(info["name"], key)
        self.firmware_type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.firmware_type_combo, 1)
        firmware_layout.addLayout(type_layout)

        path_layout = QHBoxLayout()
        self.firmware_path_label = QLabel(tr("firmware_path") + ":")
        path_layout.addWidget(self.firmware_path_label)

        self.firmware_path_edit = QLineEdit()
        self.firmware_path_edit.setReadOnly(True)
        path_layout.addWidget(self.firmware_path_edit, 1)

        self.browse_btn = QPushButton(tr("btn_browse"))
        self.browse_btn.clicked.connect(self._browse_firmware)
        path_layout.addWidget(self.browse_btn)

        firmware_layout.addLayout(path_layout)
        layout.addWidget(firmware_group)

        progress_group = QGroupBox(tr("upgrade_progress"))
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(30)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                text-align: center;
                font-size: 14px;
                font-weight: bold;
                background-color: {COLORS['bg_light']};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['accent']}, stop:1 {COLORS['success']});
                border-radius: 6px;
            }}
            """
        )
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel(tr("dfu_ready"))
        self.status_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {COLORS['text_primary']}; padding: 8px;"
        )
        self.status_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.status_label)

        self.state_label = QLabel(tr("dfu_state_prefix") + tr("dfu_state_idle"))
        self.state_label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 4px;")
        self.state_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.state_label)

        layout.addWidget(progress_group)

        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton(tr("btn_start_upgrade"))
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px 24px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_hover']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
                color: {COLORS['text_secondary']};
            }}
            """
        )
        self.start_btn.clicked.connect(self._start_upgrade)
        btn_layout.addWidget(self.start_btn)

        self.reset_btn = QPushButton(tr("btn_reset_dfu"))
        self.reset_btn.setMinimumHeight(40)
        self.reset_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['warning']};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: #e67e22;
            }}
            """
        )
        self.reset_btn.clicked.connect(self._reset_dfu_state)
        btn_layout.addWidget(self.reset_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        self._on_type_changed(0)

    def update_texts(self):
        self.warning_title_label.setText(tr("dfu_warning_title"))
        self.warning_text_label.setText(f"{tr('dfu_warning_1')}\n{tr('dfu_warning_2')}\n{tr('dfu_warning_3')}")
        self.device_group.setTitle(tr("device_info"))
        self.firmware_type_label.setText(tr("firmware_type") + ":")
        self.firmware_path_label.setText(tr("firmware_path") + ":")
        self.browse_btn.setText(tr("btn_browse"))
        self.start_btn.setText(tr("btn_start_upgrade"))
        self.reset_btn.setText(tr("btn_reset_dfu"))
        self.reset_btn.setToolTip(tr("dfu_reset_tooltip"))

    def set_device(self, device, slave_id, device_info, shared_data=None):
        self.shared_data = shared_data

        if device_info:
            hw_type = str(device_info.hardware_type).replace("StarkHardwareType.", "")
            self.device_type_label.setText(f"{tr('device_type')}: {hw_type}")
            self.firmware_version_label.setText(
                f"{tr('current_firmware')}: {device_info.firmware_version}"
            )

            for i in range(self.firmware_type_combo.count()):
                key = self.firmware_type_combo.itemData(i)
                if key and (hw_type in key or hw_type.startswith(key)):
                    self.firmware_type_combo.setCurrentIndex(i)
                    break
        else:
            self.device_type_label.setText(tr("device_type_none"))
            self.firmware_version_label.setText(tr("current_firmware_none"))

    def _on_type_changed(self, index):
        key = self.firmware_type_combo.currentData()
        if key and key in FIRMWARE_TYPES:
            saved_path = self.settings.value(f"last_firmware_path_{key}", "")
            if saved_path and os.path.exists(saved_path):
                self.firmware_path_edit.setText(saved_path)
                return
            info = FIRMWARE_TYPES[key]
            default_path = info.get("default_path")
            if default_path and default_path.exists():
                self.firmware_path_edit.setText(str(default_path))
            else:
                self.firmware_path_edit.clear()

    def _browse_firmware(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_firmware_file_title"),
            "",
            "Binary Files (*.bin *.ota);;All Files (*)",
        )
        if filename:
            self.firmware_path_edit.setText(filename)
            key = self.firmware_type_combo.currentData()
            if key:
                self.settings.setValue(f"last_firmware_path_{key}", filename)

    def _start_upgrade(self):
        if not self.device:
            QMessageBox.warning(self, tr("error_title"), tr("error_no_device"))
            return

        if self._dfu_thread is not None:
            QMessageBox.warning(self, tr("error_title"), tr("dfu_status_warning"))
            return

        firmware_path = self.firmware_path_edit.text()
        if not firmware_path or not os.path.exists(firmware_path):
            QMessageBox.warning(self, tr("error_title"), tr("error_invalid_file"))
            return

        reply = QMessageBox.question(
            self,
            tr("dfu_confirm_title"),
            tr("dfu_confirm_msg"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.start_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.firmware_type_combo.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText(tr("dfu_upgrading"))
        self.status_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #3498db; padding: 8px;"
        )
        self.state_label.setText(tr("dfu_state_prefix") + tr("dfu_state_starting"))

        if self.shared_data:
            self.shared_data.stop()

        self.dfu_started.emit()
        self._launch_worker(firmware_path)

    def _launch_worker(self, firmware_path: str):
        self._dfu_thread = QThread(self)
        self._dfu_worker = DfuWorker(self.device, self.slave_id, firmware_path, wait_secs=4)
        self._dfu_worker.moveToThread(self._dfu_thread)

        self._dfu_thread.started.connect(self._dfu_worker.run)
        self._dfu_worker.progress.connect(self._on_progress)
        self._dfu_worker.state_changed.connect(self._on_state_changed)
        self._dfu_worker.finished.connect(self._on_worker_finished)
        self._dfu_worker.finished.connect(self._dfu_thread.quit)
        self._dfu_thread.finished.connect(self._cleanup_worker)

        self._dfu_thread.start()

    def _on_progress(self, percent: int):
        self.progress_bar.setValue(percent)
        self.status_label.setText(tr("dfu_upgrading_progress").format(percent=percent))

    def _on_state_changed(self, state: int):
        state_key = DFU_STATE_NAMES.get(state, "dfu_state_unknown")
        if state_key == "dfu_state_unknown":
            state_name = tr(state_key).format(state=state)
        else:
            state_name = tr(state_key)
        self.state_label.setText(tr("dfu_state_prefix") + state_name)

    def _on_worker_finished(self, success: bool, message: str):
        self._on_finished(success, message if not success else tr("dfu_success_reboot"))

    def _cleanup_worker(self):
        if self._dfu_worker is not None:
            self._dfu_worker.deleteLater()
            self._dfu_worker = None
        if self._dfu_thread is not None:
            self._dfu_thread.deleteLater()
            self._dfu_thread = None

    def _on_finished(self, success, message):
        self.start_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.firmware_type_combo.setEnabled(True)

        self.dfu_finished.emit(success)

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText(tr("dfu_success_short"))
            self.status_label.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #28a745; padding: 8px;"
            )
            self.state_label.setText(tr("dfu_state_prefix") + tr("dfu_state_completed"))
        else:
            self.status_label.setText(tr("dfu_failed_short"))
            self.status_label.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #dc3545; padding: 8px;"
            )
            QTimer.singleShot(
                100, lambda: QMessageBox.warning(self, tr("error_title"), message)
            )

    def _reset_dfu_state(self):
        if not self.device:
            QMessageBox.warning(self, tr("error_title"), tr("error_no_device"))
            return

        try:
            device = self.device
            slave_id = self.slave_id

            async def do_reset():
                await device.reset_dfu_state(slave_id)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(do_reset())
            finally:
                loop.close()

            self.progress_bar.setValue(0)
            self.status_label.setText(tr("dfu_state_reset"))
            self.status_label.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {COLORS['text_primary']}; padding: 8px;"
            )
            self.state_label.setText(tr("dfu_state_prefix") + tr("dfu_state_idle"))

            QMessageBox.information(
                self, tr("dfu_reset_success_title"), tr("dfu_reset_success_msg")
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            QMessageBox.warning(
                self, tr("error_title"), tr("dfu_reset_fail_msg").format(error=str(e))
            )
