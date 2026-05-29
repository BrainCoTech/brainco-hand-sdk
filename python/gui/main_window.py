"""Modern Main Window"""

import asyncio
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu, QMessageBox,
    QLabel, QFrame, QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QPainter, QColor

from .i18n import get_i18n, tr
from .styles import COLORS
from .connection_panel import ConnectionPanel, run_in_new_loop
from .motor_control_panel import MotorControlPanel
from .universal_touch_panel import UniversalTouchPanel
from .data_collector_panel import DataCollectorPanel
from .system_config_panel import SystemConfigPanel
from .action_sequence_panel import ActionSequencePanel
from .timing_test_panel import TimingTestPanel
from .dfu_panel import DfuPanel
from .shared_data import SharedDataManager

# Add parent directory to path for SDK import
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk, has_touch, is_protobuf_device


class DfuOverlay(QWidget):
    """Semi-transparent overlay shown during DFU upgrade - covers entire window"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))  # Semi-transparent black

        # Draw warning text
        painter.setPen(QColor(255, 193, 7))  # Warning yellow
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, tr("dfu_overlay_warning"))

    def show_overlay(self, parent_widget):
        """Show overlay covering the parent widget"""
        self.setParent(parent_widget)
        self.setGeometry(parent_widget.rect())
        self.raise_()
        self.show()

    def hide_overlay(self):
        self.hide()


class MainWindow(QMainWindow):
    """Modern Main Window"""

    def __init__(self, mock_type=None):
        super().__init__()
        self.i18n = get_i18n()
        self.i18n.language_changed.connect(self._on_language_changed)

        self.device = None
        self.slave_id = 1
        self.protocol = None
        self.mock_type = mock_type

        # Shared data manager for all panels
        self.shared_data = SharedDataManager()
        
        # VisionTouch window (lazy initialization)
        self.vision_touch_window = None

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

        # Apply saved language preference on startup
        if self.i18n.current_language == "zh":
            self.lang_btn.setText("🌐 中")
            self.lang_zh_action.setChecked(True)
            self._on_language_changed("zh")
        else:
            self._update_texts()

        # Set window properties
        sdk_version = getattr(sdk, "__version__", "Unknown") if sdk else "Unknown"
        self.sdk_version = sdk_version
        self.setWindowTitle(f"Stark SDK (v{sdk_version})")
        self.setMinimumSize(1000, 700)
        self.showMaximized()

    def _setup_ui(self):
        """Setup modern UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout with margins
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Connection panel at top
        self.connection_panel = ConnectionPanel(mock_type=self.mock_type)
        self.connection_panel.connected.connect(self._on_connected)
        self.connection_panel.about_to_disconnect.connect(self._on_about_to_disconnect)
        self.connection_panel.disconnected.connect(self._on_disconnected)
        main_layout.addWidget(self.connection_panel)

        # Tab widget for main content
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.setDocumentMode(False)  # We use custom pane borders now instead of document mode
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        # Create panels - ordered by usage frequency
        # Common operations
        self.motor_panel = MotorControlPanel()
        self.tabs.addTab(self.motor_panel, "🎮 " + tr("motor_control"))

        # Unified Touch Sensor Panel
        self.touch_panel = UniversalTouchPanel()
        self.tabs.addTab(self.touch_panel, "👆 " + tr("touch_sensor"))

        # Testing & debugging
        self.timing_panel = TimingTestPanel()
        self.tabs.addTab(self.timing_panel, "\u23f1 " + tr("timing_test"))

        self.action_panel = ActionSequencePanel()
        self.tabs.addTab(self.action_panel, "🎬 " + tr("action_sequence"))

        self.dfu_panel = DfuPanel()
        self.dfu_panel.dfu_started.connect(self._on_dfu_started)
        self.dfu_panel.dfu_finished.connect(self._on_dfu_finished)
        self.tabs.addTab(self.dfu_panel, "🔄 " + tr("dfu_upgrade"))

        self.config_panel = SystemConfigPanel()
        self.tabs.addTab(self.config_panel, "\u2699 " + tr("system_config"))

        # Data collector panel (not in tabs, opened from menu)
        self.collector_panel = DataCollectorPanel()

        # DFU overlay (will be shown on central widget during upgrade)
        self.dfu_overlay = DfuOverlay()

    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()

        # File menu
        self.file_menu = menubar.addMenu("File")

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

        # View menu
        self.view_menu = menubar.addMenu("View")

        # Language submenu
        self.lang_menu = self.view_menu.addMenu("Language")

        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)

        self.lang_en_action = QAction("English", self)
        self.lang_en_action.setCheckable(True)
        self.lang_en_action.setChecked(True)
        self.lang_en_action.triggered.connect(lambda: self.i18n.set_language("en"))
        lang_group.addAction(self.lang_en_action)
        self.lang_menu.addAction(self.lang_en_action)

        self.lang_zh_action = QAction("中文", self)
        self.lang_zh_action.setCheckable(True)
        self.lang_zh_action.triggered.connect(lambda: self.i18n.set_language("zh"))
        lang_group.addAction(self.lang_zh_action)
        self.lang_menu.addAction(self.lang_zh_action)

        # Tools menu
        self.tools_menu = menubar.addMenu("Tools")

        self.data_collector_action = QAction("📊 Data Collection...", self)
        self.data_collector_action.triggered.connect(self._show_data_collector)
        self.tools_menu.addAction(self.data_collector_action)

        # VisionTouch window action
        self.vision_touch_action = QAction("📷 VisionTouch Sensor...", self)
        self.vision_touch_action.triggered.connect(self._show_vision_touch)
        self.tools_menu.addAction(self.vision_touch_action)

        # Help menu
        self.help_menu = menubar.addMenu("Help")

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about)
        self.help_menu.addAction(self.about_action)

    def _setup_statusbar(self):
        """Setup status bar"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # Device info label (right side - ID and firmware version)
        self.device_info_label = QLabel("")
        self.device_info_label.setStyleSheet(f"color: {COLORS['text_muted']}; margin-right: 10px;")
        self.statusbar.addPermanentWidget(self.device_info_label)  # Permanent stays visible during showMessage

        # Language switch button (right side)
        from PySide6.QtWidgets import QPushButton
        self.lang_btn = QPushButton("🌐 EN")
        self.lang_btn.setFixedWidth(60)
        self.lang_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 2px 8px;
                background: transparent;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.lang_btn.clicked.connect(self._toggle_language)
        self.statusbar.addPermanentWidget(self.lang_btn)

    def _on_tab_changed(self, index):
        """Tab changed - sync controls to current values"""
        current_widget = self.tabs.widget(index)

        # Sync motor control sliders when switching to motor panel
        if current_widget == self.motor_panel:
            self.motor_panel.sync_sliders_to_current()

        # Dynamic frequency: give full bandwidth to active tab's data
        if hasattr(self, 'shared_data') and self.shared_data and self.shared_data.data_collector:
            if current_widget == self.touch_panel:
                self.shared_data.data_collector.update_motor_frequency(0)    # disable motor
                self.shared_data.data_collector.update_touch_frequency(20)   # 20Hz touch
            else:
                self.shared_data.data_collector.update_motor_frequency(200)  # 200Hz motor
                self.shared_data.data_collector.update_touch_frequency(0)    # disable touch

    def _toggle_language(self):
        """Toggle between English and Chinese"""
        if self.i18n.current_language == "en":
            self.i18n.set_language("zh")
            self.lang_btn.setText("🌐 中")
        else:
            self.i18n.set_language("en")
            self.lang_btn.setText("🌐 EN")

    def _update_texts(self):
        """Update all texts"""
        if self.device is None:
            self.statusbar.showMessage(tr("ready"))

    def _on_language_changed(self, lang):
        """Language changed"""
        self._update_texts()

        # Update panels
        self.connection_panel.update_texts()
        self.motor_panel.update_texts()
        self.touch_panel.update_texts()
        self.collector_panel.update_texts()
        self.action_panel.update_texts()
        self.timing_panel.update_texts()
        self.dfu_panel.update_texts()
        self.config_panel.update_texts()

        # Update tab names
        tab_names = [
            (self.motor_panel, "🎮 " + tr("motor_control")),
            (self.touch_panel, "👆 " + tr("touch_sensor")),
            (self.timing_panel, "\u23f1 " + tr("timing_test")),
            (self.action_panel, "🎬 " + tr("action_sequence")),
            (self.dfu_panel, "🔄 " + tr("dfu_upgrade")),
            (self.config_panel, "\u2699 " + tr("system_config")),
        ]
        for panel, name in tab_names:
            idx = self.tabs.indexOf(panel)
            if idx >= 0:
                self.tabs.setTabText(idx, name)

        # Update menus
        self.file_menu.setTitle(tr("menu_file"))
        self.exit_action.setText(tr("menu_exit"))
        self.help_menu.setTitle(tr("menu_help"))
        self.about_action.setText(tr("menu_about"))

    def _on_about_to_disconnect(self):
        """Stop DataCollector before serial port is closed"""
        self.shared_data.stop()

    def _on_connected(self, device, slave_id, device_info, protocol_key, protocol):
        """Device connected"""
        self.device = device
        self.slave_id = slave_id
        self.protocol = protocol

        # Get hardware type once
        hw_type = getattr(device_info, 'hardware_type', None) if device_info else None
        print(f"DEBUG: hw_type={hw_type}")
        
        # Update title if mock
        if "Mock" in protocol:
            self.setWindowTitle(f"Stark SDK (v{self.sdk_version}) - MOCK")
        else:
            self.setWindowTitle(f"Stark SDK (v{self.sdk_version})")

        # Enable tabs
        self.tabs.setEnabled(True)

        # Block tab signals while adjusting visibility to prevent auto-switching
        self.tabs.blockSignals(True)

        # Determine protocol-based visibility
        is_ethercat = (protocol_key == "ethercat")

        # Show/hide tabs based on device capability
        touch_tab_index = self.tabs.indexOf(self.touch_panel)
        action_tab_index = self.tabs.indexOf(self.action_panel)
        dfu_tab_index = self.tabs.indexOf(self.dfu_panel)
        config_tab_index = self.tabs.indexOf(self.config_panel)

        # Determine if device has touch and what type
        has_touch_sensor = has_touch(hw_type)
        # removed is_pressure
        is_protobuf = is_protobuf_device(hw_type)

        # Show unified touch panel for devices with touch
        if touch_tab_index >= 0:
            self.tabs.setTabVisible(touch_tab_index, has_touch_sensor)

        # Hide Action Sequence panel for Protobuf devices (not supported) and EtherCAT
        if action_tab_index >= 0:
            self.tabs.setTabVisible(action_tab_index, not is_protobuf and not is_ethercat)

        # Hide DFU and Settings panels for EtherCAT (not applicable via GUI)
        if dfu_tab_index >= 0:
            self.tabs.setTabVisible(dfu_tab_index, not is_ethercat)
        if config_tab_index >= 0:
            self.tabs.setTabVisible(config_tab_index, not is_ethercat)

        motor_tab_index = self.tabs.indexOf(self.motor_panel)
        if motor_tab_index >= 0:
            self.tabs.setTabVisible(motor_tab_index, True)

        timing_tab_index = self.tabs.indexOf(self.timing_panel)
        if timing_tab_index >= 0:
            self.tabs.setTabVisible(timing_tab_index, True)

        # Setup shared data manager
        self.shared_data.set_device(device, slave_id, device_info)
        self.shared_data.connection_lost.connect(self._on_connection_lost)
        self.shared_data.start()

        # Pass device and shared_data to panels
        self.motor_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.touch_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.collector_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.action_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.timing_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.dfu_panel.set_device(device, slave_id, device_info, self.shared_data)
        self.config_panel.set_device(device, slave_id, device_info, protocol, self.shared_data)

        # Connect slave_id_changed signal
        self.config_panel.slave_id_changed.connect(self._on_slave_id_changed)

        # Update status bar
        if device_info:
            fw_ver = getattr(device_info, 'firmware_version', None)
            fw_str = f"v{fw_ver}" if fw_ver else ""
            device_id = f"ID:{slave_id}"
            hw_str = hw_type.name if hw_type and hasattr(hw_type, 'name') else ""

            # Update permanent device info label
            info_parts = [p for p in [hw_str, device_id, fw_str] if p]
            self.device_info_label.setText(" | ".join(info_parts))

            self.statusbar.showMessage(
                f"Connected: {device_info.serial_number} | {protocol} | FW: {fw_str}"
            )
        else:
            self.device_info_label.setText(f"ID:{slave_id}")
            self.statusbar.showMessage(f"Connected via {protocol}")

        # Switch to the motor panel and restore tab signals
        if motor_tab_index >= 0:
            self.tabs.setCurrentIndex(motor_tab_index)
        self.tabs.blockSignals(False)

    def _on_disconnected(self):
        """Device disconnected"""
        # Disconnect connection_lost signal to avoid issues on reconnect
        try:
            self.shared_data.connection_lost.disconnect(self._on_connection_lost)
        except RuntimeError:
            pass  # Signal was not connected

        # Disconnect slave_id_changed signal
        try:
            self.config_panel.slave_id_changed.disconnect(self._on_slave_id_changed)
        except RuntimeError:
            pass  # Signal was not connected

        # Stop shared data manager BEFORE serial port is closed
        # (DataCollector holds Arc ref to ctx, must stop first to release it)
        self.shared_data.stop()
        self.shared_data.clear_device()

        self.device = None
        self.slave_id = 1
        self.protocol = None

        # Clear device from panels (stops timers)
        self.motor_panel.clear_device()
        self.touch_panel.clear_device()
        self.collector_panel.clear_device()

        # Show all tabs again (will be filtered on next connect)
        for panel in [self.touch_panel,
                      self.collector_panel, self.action_panel, self.timing_panel,
                      self.dfu_panel, self.config_panel]:
            idx = self.tabs.indexOf(panel)
            if idx >= 0:
                self.tabs.setTabVisible(idx, True)
        motor_idx = self.tabs.indexOf(self.motor_panel)
        if motor_idx >= 0:
            self.tabs.setTabVisible(motor_idx, True)

        # Update status bar
        self.device_info_label.setText("")
        self.statusbar.showMessage(tr("status_disconnected"))

    def _on_connection_lost(self):
        """Handle physical disconnection (cable unplugged, power off)"""
        print("[MainWindow] Connection lost detected")

        # Show warning in status bar
        self.statusbar.showMessage(tr("status_connection_lost"))

        # Trigger disconnect cleanup via connection panel
        self.connection_panel._on_disconnect()

    def _on_slave_id_changed(self, new_id):
        """Handle slave_id change from config panel (Revo2 takes effect immediately)"""
        print(f"[MainWindow] Slave ID changed to {new_id}")
        self.slave_id = new_id

        # Update shared data manager (will restart data collector)
        self.shared_data.update_slave_id(new_id)

        # Update connection panel
        self.connection_panel.slave_id = new_id

        # Update status bar device info
        current_text = self.device_info_label.text()
        if "ID:" in current_text:
            import re
            new_text = re.sub(r'ID:\d+', f'ID:{new_id}', current_text)
            self.device_info_label.setText(new_text)

        self.statusbar.showMessage(f"Slave ID changed to {new_id}")

    def _on_dfu_started(self):
        """DFU upgrade started - lock UI to prevent interference"""
        # Stop shared data manager during DFU
        self.shared_data.stop()

        # Stop timers in panels to avoid conflicts during DFU
        self.motor_panel.clear_device()
        self.touch_panel.clear_device()
        self.collector_panel.clear_device()

        # Disable all tabs except DFU
        dfu_index = self.tabs.indexOf(self.dfu_panel)
        self.tabs.setCurrentIndex(dfu_index)
        for i in range(self.tabs.count()):
            if i != dfu_index:
                self.tabs.setTabEnabled(i, False)

        # Disable connection controls
        self.connection_panel.disconnect_btn.setEnabled(False)
        self.connection_panel.auto_detect_btn.setEnabled(False)

        self.statusbar.showMessage(tr("dfu_status_warning"))

    def _on_dfu_finished(self, success):
        """DFU upgrade finished - unlock UI and auto-reconnect"""
        # Re-enable all tabs
        for i in range(self.tabs.count()):
            self.tabs.setTabEnabled(i, True)

        # Re-enable connection controls
        self.connection_panel.disconnect_btn.setEnabled(True)
        self.connection_panel.auto_detect_btn.setEnabled(True)

        if success:
            self.statusbar.showMessage(tr("dfu_wait_reconnect"))

            # Auto-reconnect after delay (device needs time to reboot)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(5000, self._auto_reconnect_after_dfu)
        else:
            self.statusbar.showMessage(tr("dfu_failed"))

    def _auto_reconnect_after_dfu(self):
        """Auto-reconnect after DFU completion"""
        self.statusbar.showMessage(tr("status_reconnecting"))

        if self.connection_panel.ctx is not None:
            self.connection_panel._on_disconnect()

        # Trigger auto-detect in connection panel
        self.connection_panel._on_auto_detect()

    def _show_data_collector(self):
        """Show data collector dialog"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("📊 Data Collection")
        dialog.resize(800, 600)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.collector_panel)

        dialog.exec()

        # Re-parent collector panel back (so it's not destroyed with dialog)
        self.collector_panel.setParent(None)

    def _show_vision_touch(self):
        """Show VisionTouch sensor window"""
        if self.vision_touch_window is None:
            try:
                from .vision_touch_window import VisionTouchWindow
                self.vision_touch_window = VisionTouchWindow(self)
            except ImportError as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "VisionTouch Not Available",
                    f"VisionTouch features require pyvitaisdk.\n\n"
                    f"Install with: pip install pyvitaisdk\n\n"
                    f"Error: {e}"
                )
                return
        
        self.vision_touch_window.show()
        self.vision_touch_window.raise_()
        self.vision_touch_window.activateWindow()

    def _show_about(self):
        """Show about dialog"""
        about_text = f"""
<h2>Stark SDK GUI</h2>
<p>Modern control interface for Stark dexterous hands</p>
<p><b>SDK Version:</b> v{self.sdk_version}</p>

<h3>Supported Protocols</h3>
<ul>
<li>Modbus/RS485</li>
<li>CAN 2.0</li>
<li>CANFD</li>
<li>EtherCAT (Linux)</li>
</ul>

<h3>Supported Devices</h3>
<ul>
<li>Revo1 Basic / Touch</li>
<li>Revo1 Advanced / AdvancedTouch</li>
<li>Revo2 Basic / Touch</li>
</ul>

<p style="color: #7f8c8d;">© 2015-2026 BrainCo Inc.</p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle("About Stark SDK")
        msg.setTextFormat(Qt.RichText)
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec()

    def closeEvent(self, event):
        """Handle window close - cleanup resources"""
        # Stop shared data manager first (this stops the data collector thread)
        self.shared_data.stop()

        # Brief delay to ensure DataCollector thread fully releases ctx Arc ref
        import time
        time.sleep(0.1)

        # Clear device from panels (stops timers)
        self.motor_panel.clear_device()
        self.touch_panel.clear_device()
        self.collector_panel.clear_device()

        # Disconnect device if connected - use sync close to avoid event loop issues
        if self.connection_panel.ctx:
            try:
                ctx = self.connection_panel.ctx
                protocol = self.connection_panel.protocol_key

                # Use sync close for CAN protocols, async for others
                if protocol in ["can", "canfd"]:
                    if hasattr(sdk, 'close_zqwl'):
                        sdk.close_zqwl()
                elif protocol == "ethercat":
                    async def close_ethercat():
                        await ctx.ec_stop_loop()
                        await ctx.close()
                    run_in_new_loop(close_ethercat)
                else:
                    if protocol == "modbus" and hasattr(sdk, 'modbus_close'):
                        run_in_new_loop(lambda: sdk.modbus_close(ctx))
                    elif hasattr(sdk, 'close_device_handler'):
                        run_in_new_loop(lambda: sdk.close_device_handler(ctx))
                    elif hasattr(ctx, 'close'):
                        run_in_new_loop(lambda: ctx.close())
            except Exception as e:
                print(f"Error closing device on exit: {e}")

            self.connection_panel.ctx = None

        self.device = None
        event.accept()
