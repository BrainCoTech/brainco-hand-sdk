"""
Glove Sensors & IMU Acquisition GUI

This is a premium, self-contained GUI tool for the glove device.
It connects via bc-edu-sdk to display:
- 6-channel Flex (bend) sensors data.
- 6-axis IMU movement data.
- 3-axis Magnetometer data.
Includes built-in Mock simulation mode, CSV session recording and marker tagging.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from qasync import QEventLoop

# Ensure current folder is in path to resolve sibling imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import SDK resources
from edu_utils import libedu, get_glove_port_name, logger
from model import FlexData, IMUData, MagData

# Configuration constants
NUM_CHANNELS = 6
BUFFER_LENGTH = 1250
IMU_BUFFER_LENGTH = 500
MAG_BUFFER_LENGTH = 500
BAUDRATE = 115200


class GloveWindow(QtWidgets.QWidget):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args
        self.cleanup_task: asyncio.Task | None = None
        self.device = None

        # Real-time data buffers
        self.flex_buffer = np.zeros((NUM_CHANNELS, BUFFER_LENGTH))
        self.imu_buffer = np.zeros((6, IMU_BUFFER_LENGTH))  # Acc X, Y, Z, Gyro X, Y, Z
        self.mag_buffer = np.zeros((3, MAG_BUFFER_LENGTH))  # Mag X, Y, Z

        # Visual objects
        self.curves: dict[str, list[Any]] = {}
        self.plots: dict[str, list[pg.PlotWidget]] = {}

        # Session Recording state
        self.recording = False
        self.rec_start_time = None
        self.rec_timer = QtCore.QTimer()
        self.rec_timer.setInterval(1000)
        self.rec_timer.timeout.connect(self._update_rec_timer)
        self.rec_files = {}
        self.rec_writers = {}
        self.current_marker = ""

        # Polling/Streaming state
        self.streaming = False

        # Telemetry sequence numbers
        self.flex_seq = 0
        self.imu_seq = 0
        self.mag_seq = 0
        self.last_rendered_flex_seq = None
        self.last_rendered_imu_seq = None
        self.last_rendered_mag_seq = None
        self.connected = False

        # UI styles and build
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._build_ui()

        # Start the GUI update timer for plotting
        self.plot_timer = QtCore.QTimer()
        self.plot_timer.setInterval(40)  # 25 FPS
        self.plot_timer.timeout.connect(self._update_plots)
        self.plot_timer.start()

    def _build_ui(self) -> None:
        self.setWindowTitle("🖐️ BrainCo Glove GUI Demo")
        self.showMaximized()
        pg.setConfigOptions(antialias=True)

        # Futuristic Dark Theme QSS stylesheet
        _CSS = """
        QWidget#root {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a0b16, stop:0.5 #0f1126, stop:1 #0a0b16);
            color: #cbd5e1;
        }
        QLabel {
            color: #94a3b8;
            font-size: 11px;
            font-weight: bold;
        }
        QGroupBox {
            font-size: 11px;
            font-weight: bold;
            background-color: rgba(13, 15, 33, 0.75);
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }

        #sys_grp {
            border: 1px solid rgba(226, 232, 240, 0.15);
        }
        #sys_grp::title {
            color: #cbd5e1;
        }

        #conn_grp {
            border: 1px solid rgba(0, 240, 255, 0.22);
        }
        #conn_grp::title {
            color: #00f0ff;
        }

        #stream_grp {
            border: 1px solid rgba(57, 255, 20, 0.18);
        }
        #stream_grp::title {
            color: #39ff14;
        }

        #rec_grp {
            border: 1px solid rgba(255, 0, 85, 0.22);
        }
        #rec_grp::title {
            color: #ff0055;
        }

        QLineEdit, QComboBox {
            background-color: #070914;
            border: 1px solid #1f2340;
            border-radius: 5px;
            color: #f8fafc;
            padding: 4px 8px;
            font-size: 11px;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 15px;
            border-left-width: 1px;
            border-left-color: #1f2340;
            border-left-style: solid;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #00f0ff;
            background-color: #0b0e24;
        }

        QPushButton {
            background-color: rgba(30, 41, 59, 0.85);
            border: 1px solid #232a3b;
            border-radius: 5px;
            color: #e2e8f0;
            padding: 5px 12px;
            font-size: 11px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #2e3b52;
            border-color: #3d4f6e;
            color: #ffffff;
        }
        QPushButton:disabled {
            background-color: rgba(15, 23, 42, 0.4);
            color: #475569;
            border-color: #171d2b;
        }

        QPushButton#connect_btn {
            background-color: rgba(0, 240, 255, 0.08);
            color: #00f0ff;
            border: 1px solid rgba(0, 240, 255, 0.3);
        }
        QPushButton#connect_btn:hover {
            background-color: rgba(0, 240, 255, 0.18);
            color: #ffffff;
            border-color: #00f0ff;
        }
        QPushButton#connect_btn[connected="true"] {
            background-color: rgba(57, 255, 20, 0.1);
            color: #39ff14;
            border-color: rgba(57, 255, 20, 0.35);
        }

        QPushButton#stream_btn {
            background-color: rgba(57, 255, 20, 0.08);
            color: #39ff14;
            border: 1px solid rgba(57, 255, 20, 0.3);
        }
        QPushButton#stream_btn:hover {
            background-color: rgba(57, 255, 20, 0.18);
            color: #ffffff;
            border-color: #39ff14;
        }
        QPushButton#stream_btn[streaming="true"] {
            background-color: rgba(255, 0, 85, 0.12);
            color: #ff0055;
            border-color: rgba(255, 0, 85, 0.45);
        }

        QPushButton#rec_btn {
            background-color: rgba(255, 0, 85, 0.08);
            color: #ff0055;
            border: 1px solid rgba(255, 0, 85, 0.3);
        }
        QPushButton#rec_btn:hover {
            background-color: rgba(255, 0, 85, 0.18);
            color: #ffffff;
            border-color: #ff0055;
        }
        QPushButton#rec_btn[recording="true"] {
            background-color: #ff0055;
            color: #ffffff;
            border-color: #ff0055;
        }

        QPushButton#connect_btn:disabled,
        QPushButton#stream_btn:disabled,
        QPushButton#rec_btn:disabled {
            background-color: rgba(255, 255, 255, 0.02);
            color: #475569;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        QCheckBox {
            color: #94a3b8;
            font-size: 11px;
            font-weight: bold;
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border-radius: 4px;
            border: 1px solid #232a3b;
            background-color: #070914;
        }
        QCheckBox::indicator:hover {
            border-color: #00f0ff;
        }
        QCheckBox::indicator:checked {
            background-color: #00f0ff;
            border: 3px solid #070914;
        }

        QTabWidget::pane {
            border: 1px solid #14172f;
            background-color: #060712;
            border-radius: 8px;
        }
        QTabBar::tab {
            background-color: #0e1124;
            color: #8f9bb3;
            border: 1px solid #14172f;
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 2px 10px;
            height: 28px;
            min-width: 125px;
            font-weight: bold;
            font-size: 11px;
            margin-right: 4px;
        }
        QTabBar::tab:selected {
            background-color: #060712;
            color: #00f0ff;
            border-bottom: 2px solid #00f0ff;
        }

        QPlainTextEdit {
            background-color: #04050a;
            border: 1px solid #101224;
            border-radius: 6px;
            color: #8da2c4;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 11px;
            padding: 4px;
        }

        QLabel#rec_time_label {
            color: #4b526d;
            font-weight: bold;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 13px;
            margin: 0 4px;
        }
        QLabel#rec_time_label[recording="true"] {
            color: #ff0055;
        }
        """
        self.setObjectName("root")
        self.setStyleSheet(_CSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── Top Control Dashboard ──────────────────────────────────────────────
        dashboard = QtWidgets.QHBoxLayout()
        dashboard.setSpacing(8)
        root.addLayout(dashboard)

        # 1. System Status Card
        sys_grp = QtWidgets.QGroupBox("💻 SYSTEM UNIT")
        sys_grp.setObjectName("sys_grp")
        sys_lay = QtWidgets.QVBoxLayout(sys_grp)
        sys_lay.setContentsMargins(12, 10, 12, 10)
        sys_lay.setSpacing(4)

        logo_lbl = QtWidgets.QLabel("🖐️ GLOVE GUI DEMO")
        logo_lbl.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 800; letter-spacing: 0.5px;")
        sys_lay.addWidget(logo_lbl)

        self.status_label = QtWidgets.QLabel("System Ready")
        self.status_label.setStyleSheet("color: #39ff14; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
        self.status_label.setMinimumWidth(165)
        sys_lay.addWidget(self.status_label)
        dashboard.addWidget(sys_grp)

        # 2. Hardware Connection Card
        conn_grp = QtWidgets.QGroupBox("📡 DEVICE HUB")
        conn_grp.setObjectName("conn_grp")
        conn_lay = QtWidgets.QHBoxLayout(conn_grp)
        conn_lay.setContentsMargins(10, 8, 10, 8)
        conn_lay.setSpacing(6)
        conn_lay.setAlignment(QtCore.Qt.AlignVCenter)

        if self.args.mock:
            self.connect_btn = QtWidgets.QPushButton("⚡ Connect Mock")
            self.connect_btn.setObjectName("connect_btn")
            self.connect_btn.setFixedHeight(28)
            self.connect_btn.clicked.connect(self._toggle_connection)
            conn_lay.addWidget(self.connect_btn)
        else:
            self.port_combo = QtWidgets.QComboBox()
            self.port_combo.setFixedWidth(135)
            self.port_combo.setFixedHeight(28)
            self.port_combo.setEditable(True)
            conn_lay.addWidget(self.port_combo)

            # Scan serial ports
            self._scan_ports()

            self.connect_btn = QtWidgets.QPushButton("Connect Device")
            self.connect_btn.setObjectName("connect_btn")
            self.connect_btn.setFixedHeight(28)
            self.connect_btn.clicked.connect(self._toggle_connection)
            conn_lay.addWidget(self.connect_btn)

        dashboard.addWidget(conn_grp)

        # 3. Stream Controls Card
        stream_grp = QtWidgets.QGroupBox("📊 FLOW ENGINE")
        stream_grp.setObjectName("stream_grp")
        stream_lay = QtWidgets.QHBoxLayout(stream_grp)
        stream_lay.setContentsMargins(10, 8, 10, 8)
        stream_lay.setSpacing(10)
        stream_lay.setAlignment(QtCore.Qt.AlignVCenter)

        self.stream_btn = QtWidgets.QPushButton("▶ Start Stream")
        self.stream_btn.setObjectName("stream_btn")
        self.stream_btn.setFixedHeight(28)
        self.stream_btn.setEnabled(False)
        self.stream_btn.clicked.connect(self._toggle_stream)
        stream_lay.addWidget(self.stream_btn)

        dashboard.addWidget(stream_grp)

        # 4. Recording Card
        rec_grp = QtWidgets.QGroupBox("⏺ TELEMETRY RECORDER")
        rec_grp.setObjectName("rec_grp")
        rec_lay = QtWidgets.QHBoxLayout(rec_grp)
        rec_lay.setContentsMargins(10, 8, 10, 8)
        rec_lay.setSpacing(6)
        rec_lay.setAlignment(QtCore.Qt.AlignVCenter)

        pid_lbl = QtWidgets.QLabel("PID:")
        pid_lbl.setFixedWidth(24)
        rec_lay.addWidget(pid_lbl)
        self.participant_edit = QtWidgets.QLineEdit("P001")
        self.participant_edit.setFixedWidth(55)
        self.participant_edit.setFixedHeight(28)
        rec_lay.addWidget(self.participant_edit)

        self.rec_btn = QtWidgets.QPushButton("REC")
        self.rec_btn.setObjectName("rec_btn")
        self.rec_btn.setFixedHeight(28)
        self.rec_btn.setEnabled(False)
        self.rec_btn.clicked.connect(self._toggle_recording)
        rec_lay.addWidget(self.rec_btn)

        self.rec_time_label = QtWidgets.QLabel("00:00")
        self.rec_time_label.setObjectName("rec_time_label")
        rec_lay.addWidget(self.rec_time_label)

        rec_lay.addSpacing(6)

        self.marker_edit = QtWidgets.QLineEdit("fist")
        self.marker_edit.setFixedWidth(80)
        self.marker_edit.setFixedHeight(28)
        self.marker_edit.setEnabled(False)
        rec_lay.addWidget(self.marker_edit)

        self.marker_btn = QtWidgets.QPushButton("Tag Marker")
        self.marker_btn.setFixedHeight(28)
        self.marker_btn.clicked.connect(self._send_marker)
        self.marker_btn.setEnabled(False)
        rec_lay.addWidget(self.marker_btn)

        rec_lay.addStretch(1)
        dashboard.addWidget(rec_grp)
        dashboard.addStretch()

        # 5. Rightmost Telemetry Seq Status Card
        seq_grp = QtWidgets.QGroupBox("📈 TELEMETRY SEQ")
        seq_grp.setObjectName("seq_grp")
        seq_lay = QtWidgets.QVBoxLayout(seq_grp)
        seq_lay.setContentsMargins(12, 6, 12, 6)
        seq_lay.setSpacing(2)

        _mono = "font-size: 11px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;"
        self.seq_flex_lbl = QtWidgets.QLabel("FLEX  seq:      —")
        self.seq_flex_lbl.setStyleSheet(f"color: #7ecfff; {_mono}")
        self.seq_imu_lbl = QtWidgets.QLabel("IMU   seq:      —")
        self.seq_imu_lbl.setStyleSheet(f"color: #7eff9e; {_mono}")
        self.seq_mag_lbl = QtWidgets.QLabel("MAG   seq:      —")
        self.seq_mag_lbl.setStyleSheet(f"color: #ffcf7e; {_mono}")

        seq_lay.addWidget(self.seq_flex_lbl)
        seq_lay.addWidget(self.seq_imu_lbl)
        seq_lay.addWidget(self.seq_mag_lbl)

        dashboard.addWidget(seq_grp)

        # ── Middle & Bottom Body ───────────────────────────────────────────────
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        root.addWidget(splitter, stretch=1)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.tabs)

        self._add_signal_tab("Flex", "flex", NUM_CHANNELS, cols=3)
        self._add_signal_tab("IMU", "imu", 6, cols=3)
        self._add_signal_tab("MAG", "mag", 3, cols=3)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(200)
        self.log_box.setMaximumHeight(85)
        splitter.addWidget(self.log_box)
        splitter.setSizes([850, 80])

        self._append_log("System", "Glove GUI initialized.")
        if self.args.mock:
            self._append_log("System", "MOCK MODE ENABLED. No physical device required.")

    def _scan_ports(self) -> None:
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []

        auto_port = get_glove_port_name()
        if auto_port:
            ports.insert(0, auto_port)

        # Add fallbacks
        for p in ["/dev/ttyUSB0", "/dev/tty.usbserial", "COM3", "COM4"]:
            if p not in ports:
                ports.append(p)

        self.port_combo.clear()
        self.port_combo.addItems(ports)

    def _append_log(self, source: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_box.appendPlainText(f"[{ts}] [{source.upper()}] {message}")

    def _add_signal_tab(self, title: str, stream: str, channels: int, cols: int) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.curves[stream] = []
        self.plots[stream] = []

        FLEX_LABELS = ["Thumb Flex", "Thumb Abd", "Index", "Middle", "Ring", "Pinky"]
        IMU_LABELS = ["Acc X", "Acc Y", "Acc Z", "Gyro X", "Gyro Y", "Gyro Z"]
        MAG_LABELS = ["Mag X", "Mag Y", "Mag Z"]

        for ch in range(channels):
            if stream == "flex":
                title_text = FLEX_LABELS[ch]
            elif stream == "imu":
                title_text = IMU_LABELS[ch]
            else:
                title_text = MAG_LABELS[ch]

            plot = pg.PlotWidget(title=title_text)
            plot.setBackground('#060712')
            plot.showGrid(x=True, y=True, alpha=0.15)
            plot.setMouseEnabled(x=False, y=False)
            plot.setMenuEnabled(False)
            plot.getPlotItem().setDownsampling(auto=True, mode='peak')
            plot.getPlotItem().setClipToView(True)

            # Stylize axes
            plot.getAxis('bottom').setPen(pg.mkPen('#232a45', width=1))
            plot.getAxis('bottom').setTextPen('#64748b')
            plot.getAxis('left').setPen(pg.mkPen('#232a45', width=1))
            plot.getAxis('left').setTextPen('#64748b')

            # Select specific high-tech palette
            if stream == "flex":
                hue = (145 + (ch * 25) % 60) % 360  # Cool glowing emerald
            elif stream == "imu":
                hue = (45 + (ch * 35) % 80) % 360
            else:
                hue = (310 + (ch * 40) % 50) % 360

            color = pg.hsvColor(hue / 360.0, 0.85, 0.95)
            curve = plot.plot(pen=pg.mkPen(color, width=1.2))

            self.curves[stream].append(curve)
            self.plots[stream].append(plot)
            layout.addWidget(plot, ch // cols, ch % cols)

        self.tabs.addTab(widget, title)

    def _toggle_connection(self) -> None:
        if self.connected:
            asyncio.ensure_future(self._disconnect_device())
        else:
            asyncio.ensure_future(self._connect_device())

    async def _connect_device(self) -> None:
        self.connect_btn.setEnabled(False)
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: #e2e8f0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

        if self.args.mock:
            await asyncio.sleep(0.8)
            self.connected = True
            self._append_log("Connection", "Connected to MOCK Glove successfully.")
            self._update_ui_connection_state(True)
        else:
            port = self.port_combo.currentText().strip()
            self._append_log("Connection", f"Connecting to Glove on {port}...")
            try:
                # Initialize device
                self.device = libedu.PyEduDevice(port, BAUDRATE)
                await self.device.start_data_stream(libedu.MessageParser("Glove-device", libedu.MsgType.Edu))

                # Setup configuration
                await self.device.get_dongle_pair_stat()
                await asyncio.sleep(0.5)

                # Configure Flex rate 50Hz
                await self.device.set_flex_config(libedu.SamplingRate.SAMPLING_RATE_50)
                await asyncio.sleep(0.5)

                # Configure IMU rate 100Hz (Calibrated data)
                await self.device.set_imu_config(libedu.ImuSampleRate.IMU_SR_100, libedu.UploadDataType.CALIBRATED_DATA)
                await asyncio.sleep(0.5)

                # Configure MAG rate 20Hz (Calibrated data)
                await self.device.set_mag_config(libedu.MagSampleRate.MAG_SR_20, libedu.UploadDataType.CALIBRATED_DATA)
                await asyncio.sleep(0.5)

                # Initialize Buffers in SDK
                libedu.set_flex_buffer_cfg(BUFFER_LENGTH)
                libedu.set_imu_buffer_cfg(IMU_BUFFER_LENGTH)
                libedu.set_mag_buffer_cfg(MAG_BUFFER_LENGTH)

                self.connected = True
                self._append_log("Connection", "Connected to Glove hardware successfully.")
                self._update_ui_connection_state(True)
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self._append_log("Connection Error", str(e))
                self.status_label.setText("Connection Failed")
                self.status_label.setStyleSheet("color: #ff0055; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
                self.connect_btn.setEnabled(True)

    async def _disconnect_device(self) -> None:
        self.connect_btn.setEnabled(False)
        if self.streaming:
            await self._stop_stream_async()

        if not self.args.mock and self.device:
            try:
                self.device.stop_data_stream()
            except Exception as e:
                logger.error(f"Disconnection error (stop serial): {e}")
                self._append_log("Disconnection Error (stop serial)", str(e))
            try:
                self.device = None
            except Exception as e:
                logger.error(f"Disconnection error: {e}")
                self._append_log("Disconnection Error", str(e))

        self.connected = False
        self._append_log("Connection", "Disconnected from Glove.")
        self._update_ui_connection_state(False)

    def _update_ui_connection_state(self, connected: bool) -> None:
        self.connect_btn.setEnabled(True)
        self.connect_btn.setProperty("connected", connected)
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.connect_btn.update()

        if connected:
            self.connect_btn.setText("Disconnect" if not self.args.mock else "⚡ Disconnect Mock")
            self.status_label.setText("CONNECTED (CLICK START)")
            self.status_label.setStyleSheet("color: #eab308; font-size: 10px; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
            self._append_log("Connection", "Please click the green 'Start Stream' button to begin real-time data visualization.")
            self.stream_btn.setEnabled(True)
        else:
            self.connect_btn.setText("Connect Device" if not self.args.mock else "⚡ Connect Mock")
            self.status_label.setText("System Ready")
            self.status_label.setStyleSheet("color: #64748b; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
            self.stream_btn.setEnabled(False)

    def _toggle_stream(self) -> None:
        if self.streaming:
            asyncio.ensure_future(self._stop_stream_async())
        else:
            asyncio.ensure_future(self._start_stream_async())

    async def _start_stream_async(self) -> None:
        if not self.connected:
            return

        self.stream_btn.setEnabled(False)
        self._append_log("Streaming", "Starting Glove sensor stream...")

        # Reset local display buffers and sequence trackers
        self.flex_buffer[:] = 0
        self.imu_buffer[:] = 0
        self.mag_buffer[:] = 0
        self.flex_seq = 0
        self.imu_seq = 0
        self.mag_seq = 0
        self.last_rendered_flex_seq = None
        self.last_rendered_imu_seq = None
        self.last_rendered_mag_seq = None

        if not self.args.mock and self.device:
            try:
                # Flush stale SDK buffers before starting stream
                libedu.get_flex_buffer(9999, clean=True)
                libedu.get_imu_calibration_buff(9999, clean=True)
                libedu.get_mag_calibration_buff(9999, clean=True)
                await self.device.start_sensor_data_stream()
            except Exception as e:
                self._append_log("Streaming Error", f"Failed to start stream: {e}")
                self.stream_btn.setEnabled(True)
                return

        self.streaming = True
        self.stream_btn.setEnabled(True)
        self.stream_btn.setText("■ Stop Stream")
        self.stream_btn.setProperty("streaming", True)
        self.stream_btn.style().unpolish(self.stream_btn)
        self.stream_btn.style().polish(self.stream_btn)
        self.stream_btn.update()

        self.rec_btn.setEnabled(True)
        self.marker_edit.setEnabled(True)
        self.marker_btn.setEnabled(True)
        self.status_label.setText("STREAMING")
        self.status_label.setStyleSheet("color: #39ff14; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

        # Start acquisition background loop
        self.cleanup_task = asyncio.create_task(self._data_acquisition_loop())

    async def _stop_stream_async(self) -> None:
        self.stream_btn.setEnabled(False)
        self._append_log("Streaming", "Stopping sensor stream...")

        if self.recording:
            self._stop_recording()

        self.streaming = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None

        if not self.args.mock and self.device:
            try:
                await self.device.stop_sensor_data_stream()
            except Exception as e:
                self._append_log("Streaming Error", f"Stop stream failed: {e}")

        self.stream_btn.setEnabled(True)
        self.stream_btn.setText("▶ Start Stream")
        self.stream_btn.setProperty("streaming", False)
        self.stream_btn.style().unpolish(self.stream_btn)
        self.stream_btn.style().polish(self.stream_btn)
        self.stream_btn.update()

        self.rec_btn.setEnabled(False)
        self.marker_edit.setEnabled(False)
        self.marker_btn.setEnabled(False)
        self.status_label.setText("CONNECTED (CLICK START)")
        self.status_label.setStyleSheet("color: #eab308; font-size: 10px; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

    async def _data_acquisition_loop(self) -> None:
        """
        Background loop reading Glove data from bc-edu-sdk buffers at 50Hz
        """
        self._append_log("Acquisition", "Started background Glove data acquisition task.")

        mock_t = 0.0
        consecutive_errors = 0
        while self.streaming:
            try:
                if self.args.mock:
                    # Mock Data Generation
                    await asyncio.sleep(0.02)
                    mock_t += 0.02

                    # Generate 1 Flex sample per 20ms (50Hz)
                    base_amplitude = 500.0 * (0.5 + 0.5 * np.sin(mock_t * 1.0))
                    flex_sample = []
                    for ch in range(NUM_CHANNELS):
                        phase = ch * 0.4
                        val = base_amplitude * (0.8 + 0.2 * np.sin(mock_t * 2.5 + phase)) + 15.0 * np.random.randn()
                        val = np.clip(val, 0, 1023)
                        flex_sample.append(val)

                        self.flex_buffer[ch] = np.roll(self.flex_buffer[ch], -1)
                        self.flex_buffer[ch][-1] = val

                    self.flex_seq += 1
                    self.seq_flex_lbl.setText(f"FLEX  seq: {self.flex_seq:>6}")
                    if self.recording:
                        self._write_csv_row("flex", [time.time(), 0] + flex_sample + [self.current_marker])

                    # IMU generation (2 samples per 20ms -> 100Hz)
                    imu_samples = []
                    for _ in range(2):
                        acc = [0.1 * np.sin(mock_t * 1.5), 0.2 * np.cos(mock_t * 2), 9.8 + 0.05 * np.random.randn()]
                        gyro = [3.0 * np.sin(mock_t * 2.0), 8.0 * np.cos(mock_t * 1.0), 1.0 * np.random.randn()]
                        imu_samples.append(acc + gyro)

                    self.imu_seq += 2
                    self.seq_imu_lbl.setText(f"IMU   seq: {self.imu_seq:>6}")
                    N_imu = len(imu_samples)
                    for i in range(6):
                        i_samples = np.array([imu_samples[idx][i] for idx in range(N_imu)])
                        self.imu_buffer[i] = np.roll(self.imu_buffer[i], -N_imu)
                        self.imu_buffer[i][-N_imu:] = i_samples

                    if self.recording:
                        for samp in imu_samples:
                            self._write_csv_row("imu", [time.time(), 0] + samp)

                    # Mag generation (1 sample per 50ms -> 20Hz -> roughly 0.4 samples per 20ms)
                    if np.random.rand() < 0.4:
                        self.mag_seq += 1
                        self.seq_mag_lbl.setText(f"MAG   seq: {self.mag_seq:>6}")
                        mag = [10.0 + 2.0 * np.sin(mock_t * 0.5), -30.0 + 3.0 * np.cos(mock_t * 0.3), 50.0 + 2.0 * np.random.randn()]
                        for i in range(3):
                            self.mag_buffer[i] = np.roll(self.mag_buffer[i], -1)
                            self.mag_buffer[i][-1] = mag[i]

                        if self.recording:
                            self._write_csv_row("mag", [time.time(), 0] + mag)
                else:
                    # Real Hardware polling
                    await asyncio.sleep(0.015)

                    # 1. Fetch Flex Buffer
                    flex_buff = libedu.get_flex_buffer(200, clean=True)
                    if flex_buff:
                        all_samples = [[] for _ in range(NUM_CHANNELS)]
                        seq_nums = []

                        for row in flex_buff:
                            flex_data = FlexData.from_data(row)
                            seq_nums.append(flex_data.seq_num)
                            channel_values = np.array_split(flex_data.channel_values, NUM_CHANNELS)

                            for ch in range(NUM_CHANNELS):
                                all_samples[ch].extend(channel_values[ch])

                        if seq_nums:
                            self.flex_seq = seq_nums[-1]
                            self.seq_flex_lbl.setText(f"FLEX  seq: {self.flex_seq:>6}")

                        N_flex = len(all_samples[0])
                        if N_flex > 0:
                            N_display = min(N_flex, BUFFER_LENGTH)
                            for ch in range(NUM_CHANNELS):
                                ch_samples = np.array(all_samples[ch], dtype=float)
                                self.flex_buffer[ch] = np.roll(self.flex_buffer[ch], -N_display)
                                self.flex_buffer[ch][-N_display:] = ch_samples[-N_display:]

                            if self.recording:
                                rows_to_write = []
                                for idx in range(N_flex):
                                    row_vals = [all_samples[ch][idx] for ch in range(NUM_CHANNELS)]
                                    rows_to_write.append([time.time(), self.flex_seq] + row_vals + [self.current_marker])
                                self._write_csv_rows("flex", rows_to_write)

                    # 2. Fetch IMU Buffer
                    imu_buff = libedu.get_imu_calibration_buff(100, clean=True)
                    if not imu_buff:
                        imu_buff = libedu.get_imu_buffer(100, clean=True)

                    if imu_buff:
                        all_imu = [[] for _ in range(6)]
                        seq_nums_imu = []

                        for row in imu_buff:
                            imu_data = IMUData.from_data(row)
                            seq_nums_imu.append(imu_data.seqnum)
                            acc = [imu_data.acc.cord_x, imu_data.acc.cord_y, imu_data.acc.cord_z]
                            gyro = [imu_data.gyro.cord_x, imu_data.gyro.cord_y, imu_data.gyro.cord_z]
                            samp = acc + gyro
                            for i in range(6):
                                all_imu[i].append(samp[i])

                        if seq_nums_imu:
                            self.imu_seq = seq_nums_imu[-1]
                            self.seq_imu_lbl.setText(f"IMU   seq: {self.imu_seq:>6}")

                        N_imu = len(all_imu[0])
                        if N_imu > 0:
                            N_display = min(N_imu, IMU_BUFFER_LENGTH)
                            for i in range(6):
                                self.imu_buffer[i] = np.roll(self.imu_buffer[i], -N_display)
                                self.imu_buffer[i][-N_display:] = all_imu[i][-N_display:]

                            if self.recording:
                                rows_to_write = []
                                for idx in range(N_imu):
                                    row_vals = [all_imu[i][idx] for i in range(6)]
                                    rows_to_write.append([time.time(), self.imu_seq] + row_vals)
                                self._write_csv_rows("imu", rows_to_write)

                    # 3. Fetch Mag Buffer
                    mag_buff = libedu.get_mag_calibration_buff(100, clean=True)
                    if not mag_buff:
                        mag_buff = libedu.get_mag_buffer(100, clean=True)

                    if mag_buff:
                        all_mag = [[] for _ in range(3)]
                        seq_nums_mag = []

                        for row in mag_buff:
                            mag_data = MagData.from_data(row)
                            seq_nums_mag.append(mag_data.seqnum)
                            mag = [mag_data.data.cord_x, mag_data.data.cord_y, mag_data.data.cord_z]
                            for i in range(3):
                                all_mag[i].append(mag[i])

                        if seq_nums_mag:
                            self.mag_seq = seq_nums_mag[-1]
                            self.seq_mag_lbl.setText(f"MAG   seq: {self.mag_seq:>6}")

                        N_mag = len(all_mag[0])
                        if N_mag > 0:
                            N_display = min(N_mag, MAG_BUFFER_LENGTH)
                            for i in range(3):
                                self.mag_buffer[i] = np.roll(self.mag_buffer[i], -N_display)
                                self.mag_buffer[i][-N_display:] = all_mag[i][-N_display:]

                            if self.recording:
                                rows_to_write = []
                                for idx in range(N_mag):
                                    row_vals = [all_mag[i][idx] for i in range(3)]
                                    rows_to_write.append([time.time(), self.mag_seq] + row_vals)
                                self._write_csv_rows("mag", rows_to_write)
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in Glove data acquisition loop ({consecutive_errors}/5): {e}")
                if consecutive_errors >= 5:
                    self._append_log("Error", f"Glove connection lost after repeated errors: {e}")
                    asyncio.create_task(self._disconnect_device())
                    break
                await asyncio.sleep(0.1)
            else:
                consecutive_errors = 0

    def _update_plots(self) -> None:
        """
        GUI timer callback updating PlotWidgets
        """
        if not self.streaming:
            return

        # Telemetry Seq labels are updated independently in the data acquisition loop

        current_tab = self.tabs.currentIndex()

        # 1. Update Flex Tab
        if current_tab == 0:
            if self.flex_seq != self.last_rendered_flex_seq:
                self.last_rendered_flex_seq = self.flex_seq
                for ch in range(NUM_CHANNELS):
                    self.curves["flex"][ch].setData(self.flex_buffer[ch])

        # 2. Update IMU Tab
        elif current_tab == 1:
            if self.imu_seq != self.last_rendered_imu_seq:
                self.last_rendered_imu_seq = self.imu_seq
                for i in range(6):
                    self.curves["imu"][i].setData(self.imu_buffer[i])

        # 3. Update Mag Tab
        elif current_tab == 2:
            if self.mag_seq != self.last_rendered_mag_seq:
                self.last_rendered_mag_seq = self.mag_seq
                for i in range(3):
                    self.curves["mag"][i].setData(self.mag_buffer[i])

    def _on_tab_changed(self, index: int) -> None:
        """
        Force redraw on tab change by resetting rendered sequence cache
        """
        self.last_rendered_flex_seq = None
        self.last_rendered_imu_seq = None
        self.last_rendered_mag_seq = None

    def _toggle_recording(self) -> None:
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        pid = self.participant_edit.text().strip()
        if not pid:
            QtWidgets.QMessageBox.warning(self, "Invalid ID", "Please enter a valid Participant ID!")
            return

        # Prepare saving folder
        rec_dir = Path("recordings")
        rec_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.rec_files = {
            "flex": rec_dir / f"glove_{pid}_{ts}_flex.csv",
            "imu": rec_dir / f"glove_{pid}_{ts}_imu.csv",
            "mag": rec_dir / f"glove_{pid}_{ts}_mag.csv",
        }

        try:
            # Initialize files and write headers
            self.rec_writers = {}

            # Flex file
            f_flex = open(self.rec_files["flex"], "w", encoding="utf-8")
            f_flex.write("Timestamp,SeqNum,Flex_1,Flex_2,Flex_3,Flex_4,Flex_5,Flex_6,Marker\n")
            self.rec_writers["flex"] = f_flex

            # IMU file
            f_imu = open(self.rec_files["imu"], "w", encoding="utf-8")
            f_imu.write("Timestamp,SeqNum,AccX,AccY,AccZ,GyroX,GyroY,GyroZ\n")
            self.rec_writers["imu"] = f_imu

            # Mag file
            f_mag = open(self.rec_files["mag"], "w", encoding="utf-8")
            f_mag.write("Timestamp,SeqNum,MagX,MagY,MagZ\n")
            self.rec_writers["mag"] = f_mag

            self.recording = True
            self.rec_start_time = time.time()
            self.rec_timer.start()

            self.rec_btn.setText("STOP")
            self.rec_btn.setProperty("recording", True)
            self.rec_btn.style().unpolish(self.rec_btn)
            self.rec_btn.style().polish(self.rec_btn)
            self.rec_btn.update()

            self.rec_time_label.setProperty("recording", True)
            self.rec_time_label.style().unpolish(self.rec_time_label)
            self.rec_time_label.style().polish(self.rec_time_label)
            self.rec_time_label.update()
            self.rec_time_label.setText("00:00")

            self.participant_edit.setEnabled(False)
            self.connect_btn.setEnabled(False)

            self._append_log("Recording", f"Glove recording started for Participant: {pid}")
            self._append_log("Recording", f"Saving session files into {rec_dir}/")
        except Exception as e:
            self._append_log("Recording Error", f"Failed to start recording: {e}")
            self._stop_recording()

    def _stop_recording(self) -> None:
        self.recording = False
        self.rec_timer.stop()

        # Close all file writers safely
        for key, writer in self.rec_writers.items():
            try:
                writer.close()
            except Exception:
                pass
        self.rec_writers.clear()

        self.rec_btn.setText("REC")
        self.rec_btn.setProperty("recording", False)
        self.rec_btn.style().unpolish(self.rec_btn)
        self.rec_btn.style().polish(self.rec_btn)
        self.rec_btn.update()

        self.rec_time_label.setProperty("recording", False)
        self.rec_time_label.style().unpolish(self.rec_time_label)
        self.rec_time_label.style().polish(self.rec_time_label)
        self.rec_time_label.update()
        self.rec_time_label.setText("00:00")

        self.participant_edit.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self._append_log("Recording", "Glove recording stopped and files successfully saved.")

    def _write_csv_row(self, key: str, values: list) -> None:
        writer = self.rec_writers.get(key)
        if writer:
            row_str = ",".join(map(str, values)) + "\n"
            writer.write(row_str)

    def _write_csv_rows(self, key: str, rows_values: list[list]) -> None:
        writer = self.rec_writers.get(key)
        if writer:
            lines = [",".join(map(str, row)) + "\n" for row in rows_values]
            writer.write("".join(lines))

    def _update_rec_timer(self) -> None:
        if not self.recording or self.rec_start_time is None:
            return
        elapsed = int(time.time() - self.rec_start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        self.rec_time_label.setText(f"{mins:02d}:{secs:02d}")

    def _send_marker(self) -> None:
        marker = self.marker_edit.text().strip()
        if marker:
            self.current_marker = marker
            self._append_log("Marker Tagged", f"Current active marker set to: '{marker}'")
        else:
            self.current_marker = ""
            self._append_log("Marker Tagged", "Active marker cleared.")

    def closeEvent(self, event) -> None:
        self.plot_timer.stop()
        if self.streaming:
            asyncio.ensure_future(self._stop_stream_async())
        event.accept()


def main() -> None:
    parser = argparse.ArgumentParser(description="Glove Acquisition GUI Demo")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic simulated data")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Allow Ctrl+C to gracefully quit the Qt event loop
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # QTimer trick: ensure Python interpreter runs periodically so signal handlers fire
    _signal_timer = QtCore.QTimer()
    _signal_timer.setInterval(200)
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start()

    win = GloveWindow(args)
    win.show()

    with loop:
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
