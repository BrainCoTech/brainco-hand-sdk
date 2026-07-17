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
BUFFER_LENGTH = 250
IMU_BUFFER_LENGTH = 125
MAG_BUFFER_LENGTH = 125
BAUDRATE = 115200

# Sensor conversion coefficients (LSB -> Physical units)
ACC_COEFFICIENT = 1.0 / 8192.0      # LSB -> g
GYRO_COEFFICIENT = 1.0 / 16.4       # LSB -> °/s
MAG_COEFFICIENT = 1.0 / 65536.0     # LSB -> Gauss

# Sampling rate config mappings
FLEX_RATES = {
    "Off": libedu.SamplingRate.SAMPLING_RATE_OFF,
    "25 Hz": libedu.SamplingRate.SAMPLING_RATE_25,
    "50 Hz": libedu.SamplingRate.SAMPLING_RATE_50,
    "100 Hz": libedu.SamplingRate.SAMPLING_RATE_100,
    "200 Hz": libedu.SamplingRate.SAMPLING_RATE_200,
}

IMU_RATES = {
    "Off": libedu.ImuSampleRate.IMU_SR_OFF,
    "25 Hz": libedu.ImuSampleRate.IMU_SR_25,
    "50 Hz": libedu.ImuSampleRate.IMU_SR_50,
    "100 Hz": libedu.ImuSampleRate.IMU_SR_100,
    "400 Hz": libedu.ImuSampleRate.IMU_SR_400,
}

MAG_RATES = {
    "Off": libedu.MagSampleRate.MAG_SR_OFF,
    "10 Hz": libedu.MagSampleRate.MAG_SR_10,
    "20 Hz": libedu.MagSampleRate.MAG_SR_20,
    "50 Hz": libedu.MagSampleRate.MAG_SR_50,
    "100 Hz": libedu.MagSampleRate.MAG_SR_100,
}


class GloveWindow(QtWidgets.QWidget):
    msg_received_signal = QtCore.Signal(str, str)
    flex_received_signal = QtCore.Signal(list)
    imu_received_signal = QtCore.Signal(list)
    imu_calibrated_received_signal = QtCore.Signal(list)
    mag_received_signal = QtCore.Signal(list)
    mag_calibrated_received_signal = QtCore.Signal(list)

    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args
        self.msg_received_signal.connect(self._handle_msg_ui_thread)
        self.flex_received_signal.connect(self._handle_flex_received_ui_thread)
        self.imu_received_signal.connect(self._handle_imu_received_ui_thread)
        self.imu_calibrated_received_signal.connect(self._handle_imu_calibrated_received_ui_thread)
        self.mag_received_signal.connect(self._handle_mag_received_ui_thread)
        self.mag_calibrated_received_signal.connect(self._handle_mag_calibrated_received_ui_thread)
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
        self.imu_source_logged = False
        self._active_acc_coef = 1.0 / 8192.0
        self._active_gyro_coef = 1.0 / 16.4
        self.calibrating_imu = False
        self._collecting_imu_calibration = False
        self._imu_calibration_samples: list[dict[str, list[int]]] = []

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

        #control_grp {
            border: 1px solid rgba(0, 240, 255, 0.22);
        }
        #control_grp::title {
            color: #00f0ff;
        }

        #config_grp {
            border: 1px solid rgba(234, 179, 8, 0.22);
        }
        #config_grp::title {
            color: #eab308;
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
            padding: 4px 24px 4px 8px;
            font-size: 11px;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            selection-background-color: #1f8cff;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 1px;
            border-left-color: #1f2340;
            border-left-style: solid;
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            background-color: rgba(15, 23, 42, 0.9);
        }
        QComboBox::down-arrow {
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #94a3b8;
            margin-right: 6px;
        }
        QComboBox QAbstractItemView {
            background-color: #070914;
            color: #e2e8f0;
            border: 1px solid rgba(234, 179, 8, 0.42);
            border-radius: 5px;
            padding: 3px;
            outline: 0;
            selection-background-color: rgba(234, 179, 8, 0.24);
            selection-color: #ffffff;
            font-size: 11px;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
        }
        QComboBox QAbstractItemView::item {
            min-height: 20px;
            padding: 3px 8px;
            border-radius: 3px;
        }
        QComboBox QAbstractItemView::item:hover {
            background-color: rgba(0, 240, 255, 0.14);
            color: #ffffff;
        }
        QComboBox QAbstractItemView::item:selected {
            background-color: rgba(234, 179, 8, 0.30);
            color: #ffffff;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #00f0ff;
            background-color: #0b0e24;
        }
        QComboBox:disabled {
            color: #475569;
            background-color: rgba(7, 9, 20, 0.55);
            border-color: #171d2b;
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

        # 1. Device Hub Card
        control_grp = QtWidgets.QGroupBox("📡 DEVICE HUB")
        control_grp.setObjectName("control_grp")
        control_lay = QtWidgets.QGridLayout(control_grp)
        control_lay.setContentsMargins(12, 10, 12, 10)
        control_lay.setSpacing(6)

        logo_lbl = QtWidgets.QLabel("🖐️ GLOVE GUI")
        logo_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")

        self.status_label = QtWidgets.QLabel("System Ready")
        self.status_label.setStyleSheet("color: #39ff14; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
        self.status_label.setMinimumWidth(110)
        self.status_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        control_lay.addWidget(logo_lbl, 0, 0)
        control_lay.addWidget(self.status_label, 0, 1)

        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.setObjectName("connect_btn")
        self.connect_btn.setFixedHeight(26)
        self.connect_btn.clicked.connect(self._toggle_connection)

        if self.args.mock:
            self.connect_btn.setText("⚡ Connect Mock")
            control_lay.addWidget(self.connect_btn, 1, 0, 1, 2)
        else:
            self.port_combo = QtWidgets.QComboBox()
            self.port_combo.setFixedHeight(26)
            self.port_combo.setEditable(True)
            self._scan_ports()
            control_lay.addWidget(self.port_combo, 1, 0)
            control_lay.addWidget(self.connect_btn, 1, 1)

        self.stream_btn = QtWidgets.QPushButton("▶ Start Stream")
        self.stream_btn.setObjectName("stream_btn")
        self.stream_btn.setFixedHeight(26)
        self.stream_btn.setEnabled(False)
        self.stream_btn.clicked.connect(self._toggle_stream)
        control_lay.addWidget(self.stream_btn, 2, 0, 1, 2)

        dashboard.addWidget(control_grp)

        # 2. Config & Metadata Card
        config_grp = QtWidgets.QGroupBox("⚙️ DEVICE & SENSOR CONFIG")
        config_grp.setObjectName("config_grp")
        config_lay = QtWidgets.QGridLayout(config_grp)
        config_lay.setContentsMargins(12, 10, 12, 10)
        config_lay.setSpacing(6)

        # Metadata Layout (Left column)
        meta_lay = QtWidgets.QVBoxLayout()
        meta_lay.setSpacing(3)

        self.dongle_stat_lbl = QtWidgets.QLabel("Pairing: Disconnected")
        self.dongle_stat_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
        self.dongle_ver_lbl = QtWidgets.QLabel("Dongle: --")
        self.dongle_ver_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
        self.glove_ver_lbl = QtWidgets.QLabel("Glove: --")
        self.glove_ver_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
        self.glove_sn_lbl = QtWidgets.QLabel("Glove SN: --")
        self.glove_sn_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

        meta_lay.addWidget(self.dongle_stat_lbl)
        meta_lay.addWidget(self.dongle_ver_lbl)
        meta_lay.addWidget(self.glove_ver_lbl)
        meta_lay.addWidget(self.glove_sn_lbl)

        # Telemetry sequence labels
        _mono = "font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;"
        self.seq_flex_lbl = QtWidgets.QLabel("FLEX  seq:      —")
        self.seq_flex_lbl.setStyleSheet(f"color: #7ecfff; {_mono}")
        self.seq_imu_lbl = QtWidgets.QLabel("IMU   seq:      —")
        self.seq_imu_lbl.setStyleSheet(f"color: #7eff9e; {_mono}")
        self.seq_mag_lbl = QtWidgets.QLabel("MAG   seq:      —")
        self.seq_mag_lbl.setStyleSheet(f"color: #ffcf7e; {_mono}")

        meta_lay.addSpacing(4)
        meta_lay.addWidget(self.seq_flex_lbl)
        meta_lay.addWidget(self.seq_imu_lbl)
        meta_lay.addWidget(self.seq_mag_lbl)

        config_lay.addLayout(meta_lay, 0, 0, 3, 1)

        # Divider frame
        divider = QtWidgets.QFrame()
        divider.setFrameShape(QtWidgets.QFrame.VLine)
        divider.setFrameShadow(QtWidgets.QFrame.Sunken)
        divider.setStyleSheet("color: rgba(234, 179, 8, 0.15);")
        config_lay.addWidget(divider, 0, 1, 3, 1)

        # Rates dropdowns (Right column)
        rate_lay = QtWidgets.QGridLayout()
        rate_lay.setSpacing(6)

        flex_lbl = QtWidgets.QLabel("Flex:")
        flex_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.flex_rate_combo = QtWidgets.QComboBox()
        self.flex_rate_combo.setFixedHeight(24)
        self.flex_rate_combo.addItems(list(FLEX_RATES.keys()))
        self.flex_rate_combo.setCurrentText("200 Hz")
        self.flex_rate_combo.currentTextChanged.connect(self._on_flex_rate_changed)

        imu_lbl = QtWidgets.QLabel("IMU:")
        imu_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.imu_rate_combo = QtWidgets.QComboBox()
        self.imu_rate_combo.setFixedHeight(24)
        self.imu_rate_combo.addItems(list(IMU_RATES.keys()))
        self.imu_rate_combo.setCurrentText("100 Hz")
        self.imu_rate_combo.currentTextChanged.connect(self._on_imu_rate_changed)

        mag_lbl = QtWidgets.QLabel("MAG:")
        mag_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.mag_rate_combo = QtWidgets.QComboBox()
        self.mag_rate_combo.setFixedHeight(24)
        self.mag_rate_combo.addItems(list(MAG_RATES.keys()))
        self.mag_rate_combo.setCurrentText("100 Hz")
        self.mag_rate_combo.currentTextChanged.connect(self._on_mag_rate_changed)

        rate_lay.addWidget(flex_lbl, 0, 0)
        rate_lay.addWidget(self.flex_rate_combo, 0, 1)
        rate_lay.addWidget(imu_lbl, 1, 0)
        rate_lay.addWidget(self.imu_rate_combo, 1, 1)
        rate_lay.addWidget(mag_lbl, 2, 0)
        rate_lay.addWidget(self.mag_rate_combo, 2, 1)

        config_lay.addLayout(rate_lay, 0, 2, 3, 1)

        self.calib_btn = QtWidgets.QPushButton("⚙️ Calibrate IMU")
        self.calib_btn.setEnabled(False)
        self.calib_btn.setFixedHeight(26)
        self.calib_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d3748;
                color: #e2e8f0;
                border: 1px solid #4a5568;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: monospace;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a5568;
            }
            QPushButton:pressed {
                background-color: #1a202c;
            }
            QPushButton:disabled {
                background-color: #1a202c;
                color: #4d5568;
                border: 1px solid #1a202c;
            }
        """)
        self.calib_btn.clicked.connect(self._start_imu_calibration)

        config_lay.addWidget(self.calib_btn, 3, 0, 1, 3)

        dashboard.addWidget(config_grp)

        # 3. Recorder Card
        rec_grp = QtWidgets.QGroupBox("⏺ TELEMETRY RECORDER")
        rec_grp.setObjectName("rec_grp")
        rec_lay = QtWidgets.QVBoxLayout(rec_grp)
        rec_lay.setContentsMargins(12, 10, 12, 10)
        rec_lay.setSpacing(8)

        row1_lay = QtWidgets.QHBoxLayout()
        row1_lay.setSpacing(6)

        pid_lbl = QtWidgets.QLabel("PID:")
        pid_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-weight: bold; font-family: monospace;")
        self.participant_edit = QtWidgets.QLineEdit("P001")
        self.participant_edit.setFixedWidth(55)
        self.participant_edit.setFixedHeight(24)

        self.rec_btn = QtWidgets.QPushButton("REC")
        self.rec_btn.setObjectName("rec_btn")
        self.rec_btn.setFixedHeight(24)
        self.rec_btn.setEnabled(False)
        self.rec_btn.clicked.connect(self._toggle_recording)

        self.rec_time_label = QtWidgets.QLabel("00:00")
        self.rec_time_label.setObjectName("rec_time_label")
        self.rec_time_label.setStyleSheet("font-family: monospace; font-size: 11px;")

        row1_lay.addWidget(pid_lbl)
        row1_lay.addWidget(self.participant_edit)
        row1_lay.addWidget(self.rec_btn)
        row1_lay.addWidget(self.rec_time_label)
        row1_lay.addStretch(1)

        row2_lay = QtWidgets.QHBoxLayout()
        row2_lay.setSpacing(6)

        tag_lbl = QtWidgets.QLabel("Tag:")
        tag_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-weight: bold; font-family: monospace;")

        self.marker_edit = QtWidgets.QLineEdit("fist")
        self.marker_edit.setFixedWidth(80)
        self.marker_edit.setFixedHeight(24)
        self.marker_edit.setEnabled(False)

        self.marker_btn = QtWidgets.QPushButton("Tag Marker")
        self.marker_btn.setFixedHeight(24)
        self.marker_btn.clicked.connect(self._send_marker)
        self.marker_btn.setEnabled(False)

        row2_lay.addWidget(tag_lbl)
        row2_lay.addWidget(self.marker_edit)
        row2_lay.addWidget(self.marker_btn)
        row2_lay.addStretch(1)

        rec_lay.addLayout(row1_lay)
        rec_lay.addLayout(row2_lay)
        rec_lay.addStretch(1)

        dashboard.addWidget(rec_grp)
        dashboard.addStretch()

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

    def _on_flex_data(self, data: list) -> None:
        try:
            self.flex_received_signal.emit(data)
        except RuntimeError:
            pass

    def _handle_flex_received_ui_thread(self, data: list) -> None:
        if not self.streaming or not data:
            return
        if self.calibrating_imu:
            return

        all_samples = [[] for _ in range(NUM_CHANNELS)]
        seq_nums_flex = []

        for row in data:
            if len(row) < NUM_CHANNELS + 1:
                continue
            seq_nums_flex.append(row[0])
            for ch in range(NUM_CHANNELS):
                all_samples[ch].append(row[ch + 1])

        if seq_nums_flex:
            self.flex_seq = int(seq_nums_flex[-1]) & 0xFFFF
            self.seq_flex_lbl.setText(f"FLEX  seq: {self.flex_seq:>6}")

            # Print active dataType to console log periodically (every 1s)
            now = time.time()
            if now - getattr(self, "_last_flex_log_time", 0) > 1.0:
                self._last_flex_log_time = now
                msg = f"Flex data stream active (seq: {self.flex_seq})"
                self._append_log("System", msg)
                logger.info(msg)

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
                    rows_to_write.append([time.time(), int(seq_nums_flex[idx]) & 0xFFFF] + row_vals + [self.current_marker])
                self._write_csv_rows("flex", rows_to_write)

    def _on_imu_data(self, data: list) -> None:
        try:
            self.imu_received_signal.emit(data)
        except RuntimeError:
            pass

    def _handle_imu_received_ui_thread(self, data: list) -> None:
        if not self.streaming or not data:
            return
        if self.calibrating_imu:
            if self._collecting_imu_calibration:
                self._collect_imu_calibration_rows(data)
            return

        all_imu = [[] for _ in range(6)]
        seq_nums_imu = []

        for row in data:
            if len(row) < 7:
                continue
            seq_nums_imu.append(row[0])

            acc = [row[1], row[2], row[3]]
            gyro = [row[4], row[5], row[6]]

            for ch in range(3):
                all_imu[ch].append(acc[ch])
                all_imu[ch + 3].append(gyro[ch])

        if seq_nums_imu:
            self.imu_seq = int(seq_nums_imu[-1]) & 0xFFFF
            self.seq_imu_lbl.setText(f"IMU   seq: {self.imu_seq:>6}")

            # Print active dataType to console log periodically (every 1s)
            now = time.time()
            if now - getattr(self, "_last_imu_log_time", 0) > 1.0:
                self._last_imu_log_time = now
                last_row = data[-1]
                acc_vals = last_row[1:4]
                gyro_vals = last_row[4:7]
                msg = (
                    f"IMU data stream active: RAW_DATA (seq: {self.imu_seq}) | "
                    f"Acc: [{acc_vals[0]:.3f}, {acc_vals[1]:.3f}, {acc_vals[2]:.3f}] g | "
                    f"Gyro: [{gyro_vals[0]:.2f}, {gyro_vals[1]:.2f}, {gyro_vals[2]:.2f}] °/s"
                )
                self._append_log("System", msg)
                logger.info(msg)

        N_imu = len(all_imu[0])
        if N_imu > 0:
            N_display = min(N_imu, IMU_BUFFER_LENGTH)
            for ch in range(6):
                ch_samples = np.array(all_imu[ch], dtype=float)
                self.imu_buffer[ch] = np.roll(self.imu_buffer[ch], -N_display)
                self.imu_buffer[ch][-N_display:] = ch_samples[-N_display:]

            if self.recording:
                rows_to_write = []
                for idx in range(N_imu):
                    row_vals = [all_imu[ch][idx] for ch in range(6)]
                    rows_to_write.append([time.time(), int(seq_nums_imu[idx]) & 0xFFFF] + row_vals)
                self._write_csv_rows("imu", rows_to_write)

    def _on_imu_data_calibrated(self, data: list) -> None:
        try:
            self.imu_calibrated_received_signal.emit(data)
        except RuntimeError:
            pass

    def _handle_imu_calibrated_received_ui_thread(self, data: list) -> None:
        if not self.streaming or not data:
            return
        if self.calibrating_imu:
            return

        all_imu = [[] for _ in range(6)]
        seq_nums_imu = []

        for row in data:
            if len(row) < 7:
                continue
            seq_nums_imu.append(row[0])

            acc = [row[1], row[2], row[3]]
            gyro = [row[4], row[5], row[6]]

            for ch in range(3):
                all_imu[ch].append(acc[ch])
                all_imu[ch + 3].append(gyro[ch])

        if seq_nums_imu:
            self.imu_seq = int(seq_nums_imu[-1]) & 0xFFFF
            self.seq_imu_lbl.setText(f"IMU   seq: {self.imu_seq:>6}")

            # Print active dataType to console log periodically (every 1s)
            now = time.time()
            if now - getattr(self, "_last_imu_log_time", 0) > 1.0:
                self._last_imu_log_time = now
                last_row = data[-1]
                acc_vals = last_row[1:4]
                gyro_vals = last_row[4:7]
                msg = (
                    f"IMU data stream active: CALIBRATED_DATA (seq: {self.imu_seq}) | "
                    f"Acc: [{acc_vals[0]:.3f}, {acc_vals[1]:.3f}, {acc_vals[2]:.3f}] g | "
                    f"Gyro: [{gyro_vals[0]:.2f}, {gyro_vals[1]:.2f}, {gyro_vals[2]:.2f}] °/s"
                )
                self._append_log("System", msg)
                logger.info(msg)

        N_imu = len(all_imu[0])
        if N_imu > 0:
            N_display = min(N_imu, IMU_BUFFER_LENGTH)
            for ch in range(6):
                ch_samples = np.array(all_imu[ch], dtype=float)
                self.imu_buffer[ch] = np.roll(self.imu_buffer[ch], -N_display)
                self.imu_buffer[ch][-N_display:] = ch_samples[-N_display:]

            if self.recording:
                rows_to_write = []
                for idx in range(N_imu):
                    row_vals = [all_imu[ch][idx] for ch in range(6)]
                    rows_to_write.append([time.time(), int(seq_nums_imu[idx]) & 0xFFFF] + row_vals)
                self._write_csv_rows("imu", rows_to_write)

    def _on_mag_data(self, data: list) -> None:
        try:
            self.mag_received_signal.emit(data)
        except RuntimeError:
            pass

    def _handle_mag_received_ui_thread(self, data: list) -> None:
        if not self.streaming or not data:
            return
        if self.calibrating_imu:
            return

        all_mag = [[] for _ in range(3)]
        seq_nums_mag = []

        for row in data:
            if len(row) < 4:
                continue
            seq_nums_mag.append(row[0])

            mag = [row[1], row[2], row[3]]
            for ch in range(3):
                all_mag[ch].append(mag[ch])

        if seq_nums_mag:
            self.mag_seq = int(seq_nums_mag[-1]) & 0xFFFF
            self.seq_mag_lbl.setText(f"MAG   seq: {self.mag_seq:>6}")

            now = time.time()
            if now - getattr(self, "_last_mag_log_time", 0) > 1.0:
                self._last_mag_log_time = now
                last_row = data[-1]
                mag_vals = last_row[1:4]
                msg = (
                    f"MAG data stream active: RAW_DATA (seq: {self.mag_seq}) | "
                    f"Mag: [{mag_vals[0]:.3f}, {mag_vals[1]:.3f}, {mag_vals[2]:.3f}] Gauss"
                )
                self._append_log("System", msg)
                logger.info(msg)

        N_mag = len(all_mag[0])
        if N_mag > 0:
            self.mag_buffer = np.roll(self.mag_buffer, -N_mag, axis=1)
            for ch in range(3):
                self.mag_buffer[ch][-N_mag:] = all_mag[ch]

            if self.recording:
                rows_to_write = []
                for idx in range(N_mag):
                    row_vals = [all_mag[ch][idx] for ch in range(3)]
                    rows_to_write.append([time.time(), int(seq_nums_mag[idx]) & 0xFFFF] + row_vals)
                self._write_csv_rows("mag", rows_to_write)

    def _on_mag_calibrated(self, data: list) -> None:
        try:
            self.mag_calibrated_received_signal.emit(data)
        except RuntimeError:
            pass

    def _handle_mag_calibrated_received_ui_thread(self, data: list) -> None:
        if not self.streaming or not data:
            return
        if self.calibrating_imu:
            return

        all_mag = [[] for _ in range(3)]
        seq_nums_mag = []

        for row in data:
            if len(row) < 4:
                continue
            seq_nums_mag.append(row[0])

            mag = [row[1], row[2], row[3]]
            for ch in range(3):
                all_mag[ch].append(mag[ch])

        if seq_nums_mag:
            self.mag_seq = int(seq_nums_mag[-1]) & 0xFFFF
            self.seq_mag_lbl.setText(f"MAG   seq: {self.mag_seq:>6}")

            now = time.time()
            if now - getattr(self, "_last_mag_log_time", 0) > 1.0:
                self._last_mag_log_time = now
                last_row = data[-1]
                mag_vals = last_row[1:4]
                msg = (
                    f"MAG data stream active: CALIBRATED_DATA (seq: {self.mag_seq}) | "
                    f"Mag: [{mag_vals[0]:.3f}, {mag_vals[1]:.3f}, {mag_vals[2]:.3f}] Gauss"
                )
                self._append_log("System", msg)
                logger.info(msg)

        N_mag = len(all_mag[0])
        if N_mag > 0:
            self.mag_buffer = np.roll(self.mag_buffer, -N_mag, axis=1)
            for ch in range(3):
                self.mag_buffer[ch][-N_mag:] = all_mag[ch]

            if self.recording:
                rows_to_write = []
                for idx in range(N_mag):
                    row_vals = [all_mag[ch][idx] for ch in range(3)]
                    rows_to_write.append([time.time(), int(seq_nums_mag[idx]) & 0xFFFF] + row_vals)
                self._write_csv_rows("mag", rows_to_write)

    def _on_msg_callback(self, device_id: str, msg_json: str) -> None:
        try:
            self.msg_received_signal.emit(device_id, msg_json)
        except RuntimeError:
            pass

    def _handle_msg_ui_thread(self, device_id: str, msg_json: str) -> None:
        try:
            import json
            data = json.loads(msg_json)
            self._append_log("Protocol", f"Resp: {msg_json}")

            if "Dongle2App" in data:
                dongle = data["Dongle2App"]
                pair_stat = dongle.get("pairingStatus") or dongle.get("pairing_status")
                if pair_stat:
                    pair_stat_str = str(pair_stat)
                    self.dongle_stat_lbl.setText(f"Pairing: {pair_stat_str}")
                    if pair_stat_str == "PAIRED" or pair_stat_str == "Paired":
                        self.dongle_stat_lbl.setStyleSheet("color: #39ff14; font-size: 10px; font-family: monospace;")
                    else:
                        self.dongle_stat_lbl.setStyleSheet("color: #ff0055; font-size: 10px; font-family: monospace;")

                dev_info = dongle.get("deviceInfo") or dongle.get("device_info")
                if dev_info:
                    fw_v = dev_info.get("fwVersion") or dev_info.get("fw_version", "--")
                    sn = dev_info.get("sn", "--")
                    self.dongle_ver_lbl.setText(f"Dongle SN: {sn} (v{fw_v})")

            elif "Sensor2App" in data:
                sensor = data["Sensor2App"]
                dev_info = sensor.get("deviceInfo") or sensor.get("device_info")
                if dev_info:
                    fw_v = dev_info.get("fwVersion") or dev_info.get("fw_version", "--")
                    sn = dev_info.get("sn", "--")
                    model = dev_info.get("model", "Glove")
                    self.glove_ver_lbl.setText(f"Glove: {model}")
                    self.glove_sn_lbl.setText(f"Glove SN: {sn} (v{fw_v})")
                    self.glove_ver_lbl.setStyleSheet("color: #39ff14; font-size: 10px; font-family: monospace;")
                    self.glove_sn_lbl.setStyleSheet("color: #39ff14; font-size: 10px; font-family: monospace;")

                imu_resp = sensor.get("imuResp") or sensor.get("imu_resp")
                if imu_resp:
                    acc_coef = imu_resp.get("accCoefficient") or imu_resp.get("acc_coefficient")
                    if acc_coef and acc_coef > 0.0:
                        self._active_acc_coef = acc_coef
                    gyro_coef = imu_resp.get("gyroCoefficient") or imu_resp.get("gyro_coefficient")
                    if gyro_coef and gyro_coef > 0.0:
                        self._active_gyro_coef = gyro_coef
        except Exception as e:
            logger.error(f"Error handling UI metadata update: {e}")

    def _start_imu_calibration(self) -> None:
        if not self.streaming or self.args.mock:
            return
        asyncio.ensure_future(self._run_imu_calibration_async())

    def _collect_imu_calibration_rows(self, rows: list[list[float]]) -> None:
        acc_coef = getattr(self, "_active_acc_coef", 1.0 / 8192.0)
        gyro_coef = getattr(self, "_active_gyro_coef", 1.0 / 16.4)
        if acc_coef <= 0.0 or gyro_coef <= 0.0:
            return

        for row in rows:
            if len(row) < 7:
                continue

            acc = [float(row[1]), float(row[2]), float(row[3])]
            gyro = [float(row[4]), float(row[5]), float(row[6])]
            if not np.all(np.isfinite(acc + gyro)):
                continue
            if any(abs(v) >= 1900.0 for v in gyro):
                continue

            self._imu_calibration_samples.append({
                "acc": [int(round(v / acc_coef)) for v in acc],
                "gyro": [int(round(v / gyro_coef)) for v in gyro],
            })

    async def _run_imu_calibration_async(self) -> None:
        self.calibrating_imu = True
        self.plot_timer.stop()
        self.calib_btn.setEnabled(False)
        self.calib_btn.setText("⏳ Calibrating (Keep Still)...")
        self._append_log("Calibration", "IMU calibration started. Please keep the glove static on the table...")

        # Get active IMU rate
        imu_rate_str = self.imu_rate_combo.currentText()
        active_imu_rate = IMU_RATES.get(imu_rate_str, libedu.ImuSampleRate.IMU_SR_100)

        # 1. Switch device to RAW_DATA mode
        switched_to_raw = False
        calibration_applied = False
        calibration_stream_started = False
        sensor_stream_stopped = False
        try:
            await self.device.stop_sensor_data_stream()
            sensor_stream_stopped = True
            await asyncio.sleep(0.2)

            await self.device.set_imu_config(active_imu_rate, libedu.UploadDataType.RAW_DATA)
            switched_to_raw = True
            await asyncio.sleep(0.3)

            libedu.set_imu_data_callback(self._on_imu_data)
            await self.device.start_sensor_data_stream()
            calibration_stream_started = True
            await asyncio.sleep(0.5)
            self._imu_calibration_samples.clear()
            self._collecting_imu_calibration = True
        except Exception as e:
            self._append_log("Calibration Error", f"Failed to enter isolated RAW_DATA sampling mode: {e}")
            try:
                libedu.set_imu_data_callback(None)
            except Exception:
                pass
            self.calib_btn.setText("⚙️ Calibrate IMU")
            self.calib_btn.setEnabled(True)
            if switched_to_raw:
                try:
                    await self.device.set_imu_config(active_imu_rate, libedu.UploadDataType.CALIBRATED_DATA)
                except Exception:
                    pass
            if sensor_stream_stopped:
                try:
                    await self.device.start_sensor_data_stream()
                except Exception:
                    pass
            self.calibrating_imu = False
            if not self.plot_timer.isActive():
                self.plot_timer.start()
            return

        try:
            await asyncio.sleep(2.5)
            self._collecting_imu_calibration = False
            valid_samples = list(self._imu_calibration_samples)

            await self.device.stop_sensor_data_stream()
            calibration_stream_started = False

            if len(valid_samples) < 30:
                self._append_log("Calibration Error", f"Too few valid samples collected ({len(valid_samples)}). Calibration failed.")
                return

            acc_x = [s["acc"][0] for s in valid_samples]
            acc_y = [s["acc"][1] for s in valid_samples]
            acc_z = [s["acc"][2] for s in valid_samples]
            gyro_x = [s["gyro"][0] for s in valid_samples]
            gyro_y = [s["gyro"][1] for s in valid_samples]
            gyro_z = [s["gyro"][2] for s in valid_samples]

            mean_acc_x = float(np.mean(acc_x))
            mean_acc_y = float(np.mean(acc_y))
            mean_acc_z = float(np.mean(acc_z))
            mean_gyro_x = float(np.mean(gyro_x))
            mean_gyro_y = float(np.mean(gyro_y))
            mean_gyro_z = float(np.mean(gyro_z))

            acc_offset = [mean_acc_x, mean_acc_y, mean_acc_z]
            gyro_offset = [mean_gyro_x, mean_gyro_y, mean_gyro_z]

            # Deduct gravity component dynamically using active coefficient (gravity in LSB = 1.0 / active_coef)
            active_coef = getattr(self, "_active_acc_coef", 1.0 / 8192.0)
            acc_offset[2] = acc_offset[2] - (1.0 / active_coef)

            self._append_log("Calibration", f"Offset calculated (LSB): Acc Offset={acc_offset}, Gyro Offset={gyro_offset}")
            self._append_log(
                "Calibration",
                (
                    f"Raw gyro stats (LSB): "
                    f"X mean={mean_gyro_x:.3f} min={min(gyro_x)} max={max(gyro_x)}, "
                    f"Y mean={mean_gyro_y:.3f} min={min(gyro_y)} max={max(gyro_y)}, "
                    f"Z mean={mean_gyro_z:.3f} min={min(gyro_z)} max={max(gyro_z)}, "
                    f"samples={len(valid_samples)}"
                ),
            )
            logger.info(f"🎯 Offset calculated (LSB): Acc Offset={acc_offset}, Gyro Offset={gyro_offset}")
            logger.info(
                "📊 Raw gyro stats (LSB): "
                f"X mean={mean_gyro_x:.3f} min={min(gyro_x)} max={max(gyro_x)}, "
                f"Y mean={mean_gyro_y:.3f} min={min(gyro_y)} max={max(gyro_y)}, "
                f"Z mean={mean_gyro_z:.3f} min={min(gyro_z)} max={max(gyro_z)}, "
                f"samples={len(valid_samples)}"
            )
            if valid_samples:
                logger.info(f"🔍 First raw sample in calibration: {valid_samples[0]}")

            # 5. Send calibration offsets to firmware (firmware expects final config to be CALIBRATED_DATA)
            try:
                await self.device.set_imu_calibration_config(
                    active_imu_rate,
                    libedu.UploadDataType.CALIBRATED_DATA,
                    acc_offset,
                    gyro_offset
                )
                calibration_applied = True
                self._append_log("Calibration", "IMU calibration parameters successfully updated in Glove firmware!")
            except Exception as e:
                self._append_log("Calibration Error", f"Failed to send calibration config to device: {e}")
        finally:
            self._collecting_imu_calibration = False
            try:
                libedu.set_imu_data_callback(None)
            except Exception:
                pass
            if calibration_stream_started:
                try:
                    await self.device.stop_sensor_data_stream()
                except Exception as e:
                    self._append_log("Calibration Error", f"Failed to stop RAW_DATA sampling stream: {e}")
            if switched_to_raw and not calibration_applied:
                try:
                    await self.device.set_imu_config(active_imu_rate, libedu.UploadDataType.CALIBRATED_DATA)
                    self._append_log("Calibration", "IMU stream restored to CALIBRATED_DATA.")
                except Exception as e:
                    self._append_log("Calibration Error", f"Failed to restore IMU CALIBRATED_DATA mode: {e}")
            if sensor_stream_stopped and self.streaming:
                try:
                    await self.device.start_sensor_data_stream()
                except Exception as e:
                    self._append_log("Calibration Error", f"Failed to restart sensor data stream: {e}")
            self.calibrating_imu = False
            if not self.plot_timer.isActive():
                self.plot_timer.start()
            self.calib_btn.setText("⚙️ Calibrate IMU")
            self.calib_btn.setEnabled(True)

    def _on_flex_rate_changed(self, text: str) -> None:
        if self.connected and not self.args.mock and self.device:
            rate = FLEX_RATES.get(text, libedu.SamplingRate.SAMPLING_RATE_200)
            asyncio.create_task(self._send_flex_config(rate))

    async def _send_flex_config(self, rate) -> None:
        try:
            await self.device.set_flex_config(rate)
            self._append_log("Config", f"Flex sampling rate changed to: {self.flex_rate_combo.currentText()}")
        except Exception as e:
            self._append_log("Config Error", f"Failed to set Flex config: {e}")

    def _on_imu_rate_changed(self, text: str) -> None:
        if self.connected and not self.args.mock and self.device:
            rate = IMU_RATES.get(text, libedu.ImuSampleRate.IMU_SR_100)
            asyncio.create_task(self._send_imu_config(rate))

    async def _send_imu_config(self, rate) -> None:
        try:
            await self.device.set_imu_config(rate, libedu.UploadDataType.CALIBRATED_DATA)
            self._append_log("Config", f"IMU sampling rate changed to: {self.imu_rate_combo.currentText()}")
        except Exception as e:
            self._append_log("Config Error", f"Failed to set IMU config: {e}")

    def _on_mag_rate_changed(self, text: str) -> None:
        if self.connected and not self.args.mock and self.device:
            rate = MAG_RATES.get(text, libedu.MagSampleRate.MAG_SR_100)
            asyncio.create_task(self._send_mag_config(rate))

    async def _send_mag_config(self, rate) -> None:
        try:
            await self.device.set_mag_config(rate, libedu.UploadDataType.CALIBRATED_DATA)
            self._append_log("Config", f"MAG sampling rate changed to: {self.mag_rate_combo.currentText()}")
        except Exception as e:
            self._append_log("Config Error", f"Failed to set MAG config: {e}")

    def _auto_connect_and_stream(self) -> None:
        if self.args.mock or not hasattr(self, "_auto_connect_port") or not self._auto_connect_port:
            return
        self._append_log("AutoPilot", f"Only one physical port detected: '{self._auto_connect_port}'. Automatically connecting...")

        async def run_auto() -> None:
            try:
                await self._connect_device()
                if self.connected:
                    self._append_log("AutoPilot", "Connection successful. Automatically starting sensor stream...")
                    await self._start_stream_async()
            except Exception as e:
                self._append_log("AutoPilot Error", f"Auto connect/stream failed: {e}")

        asyncio.ensure_future(run_auto())

    def _scan_ports(self) -> None:
        try:
            import serial.tools.list_ports
            ports = [
                p.device for p in serial.tools.list_ports.comports()
                if "debug-console" not in p.device
                and "cu." not in p.device
                and "bluetooth" not in p.device.lower()
            ]
        except Exception:
            ports = []

        auto_port = get_glove_port_name()
        if auto_port and auto_port not in ports:
            ports.insert(0, auto_port)

        real_port_count = len(ports)
        self._auto_connect_port = ports[0] if real_port_count == 1 else None

        # Add fallbacks
        for p in ["/dev/ttyUSB0", "/dev/tty.usbserial", "COM3", "COM4"]:
            if p not in ports:
                ports.append(p)

        self.port_combo.clear()
        self.port_combo.addItems(ports)

        if self._auto_connect_port:
            QtCore.QTimer.singleShot(500, self._auto_connect_and_stream)

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

            # Set physical units labels on left axis
            if stream == "flex":
                plot.setLabel('left', 'Value', units='ADC')
            elif stream == "imu":
                if ch < 3:
                    plot.setLabel('left', 'Acc', units='g')
                else:
                    plot.setLabel('left', 'Gyro', units='°/s')
            elif stream == "mag":
                plot.setLabel('left', 'Mag', units='Gauss')

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
                # NOTE: This step-by-step manual sequence (open_serial_stream -> set_configs -> start_sensor_data_stream)
                # is an advanced path for custom lifecycles. For general use cases, the new high-level
                # EduDevice.start_stream(...) API using SensorProfile is strongly recommended as the preferred default.
                self.device = libedu.EduDevice(port, BAUDRATE)
                await self.device.open_serial_stream(libedu.MessageParser("Glove-device", libedu.MsgType.Edu))

                # Register message response callback
                libedu.set_msg_resp_callback(self._on_msg_callback)

                # Query Dongle and Device Metadata
                self._append_log("Connection", "Querying Dongle and Device metadata...")
                await self.device.get_dongle_info()
                await asyncio.sleep(0.15)
                await self.device.get_dongle_pair_stat()
                await asyncio.sleep(0.15)
                await self.device.get_device_info()
                await asyncio.sleep(0.2)

                # Configure Flex rate
                flex_rate_str = self.flex_rate_combo.currentText()
                flex_rate = FLEX_RATES.get(flex_rate_str, libedu.SamplingRate.SAMPLING_RATE_200)
                await self.device.set_flex_config(flex_rate)
                await asyncio.sleep(0.5)

                # Configure IMU rate (Calibrated data)
                imu_rate_str = self.imu_rate_combo.currentText()
                imu_rate = IMU_RATES.get(imu_rate_str, libedu.ImuSampleRate.IMU_SR_100)
                await self.device.set_imu_config(imu_rate, libedu.UploadDataType.CALIBRATED_DATA)
                await asyncio.sleep(0.5)

                # Configure MAG rate (Calibrated data)
                mag_rate_str = self.mag_rate_combo.currentText()
                mag_rate = MAG_RATES.get(mag_rate_str, libedu.MagSampleRate.MAG_SR_100)
                await self.device.set_mag_config(mag_rate, libedu.UploadDataType.CALIBRATED_DATA)
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
                await self.device.stop_stream()
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
            self.status_label.setText("DISCONNECTED")
            self.status_label.setStyleSheet("color: #6b7280; font-size: 10px; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
            self.stream_btn.setEnabled(False)

            # Reset metadata labels
            self.dongle_stat_lbl.setText("Pairing: Disconnected")
            self.dongle_stat_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
            self.dongle_ver_lbl.setText("Dongle: --")
            self.glove_ver_lbl.setText("Glove: --")
            self.glove_ver_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")
            self.glove_sn_lbl.setText("Glove SN: --")
            self.glove_sn_lbl.setStyleSheet("color: #a0aec0; font-size: 10px; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

            # Reset sequence labels
            self.seq_flex_lbl.setText("FLEX  seq:      —")
            self.seq_imu_lbl.setText("IMU   seq:      —")
            self.seq_mag_lbl.setText("MAG   seq:      —")

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
                libedu.set_flex_data_callback(self._on_flex_data)
                libedu.set_imu_data_callback(None)
                libedu.set_imu_calibration_data_callback(self._on_imu_data_calibrated)
                libedu.set_mag_data_callback(None)
                libedu.set_mag_calibration_data_callback(self._on_mag_calibrated)
                self.streaming = True
                self._append_log("Streaming", "Sending START_DATA_STREAM command...")
                await self.device.start_sensor_data_stream()
                self._append_log("Streaming", "START_DATA_STREAM command sent.")
            except Exception as e:
                self.streaming = False
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
        if not self.args.mock:
            self.calib_btn.setEnabled(True)
        self.marker_edit.setEnabled(True)
        self.marker_btn.setEnabled(True)
        self.status_label.setText("STREAMING")
        self.status_label.setStyleSheet("color: #39ff14; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

        if self.args.mock:
            self.cleanup_task = asyncio.create_task(self._data_acquisition_loop())

    async def _stop_stream_async(self) -> None:
        self.stream_btn.setEnabled(False)
        self._append_log("Streaming", "Stopping sensor stream...")

        if self.recording:
            self._stop_recording()

        self.streaming = False
        self.imu_source_logged = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None

        if not self.args.mock and self.device:
            try:
                libedu.set_flex_data_callback(None)
                libedu.set_imu_data_callback(None)
                libedu.set_imu_calibration_data_callback(None)
                libedu.set_mag_data_callback(None)
                libedu.set_mag_calibration_data_callback(None)
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
        self.calib_btn.setEnabled(False)
        self.marker_edit.setEnabled(False)
        self.marker_btn.setEnabled(False)
        self.status_label.setText("CONNECTED (CLICK START)")
        self.status_label.setStyleSheet("color: #eab308; font-size: 10px; font-weight: bold; font-family: 'Menlo', 'Monaco', 'Consolas', monospace;")

    async def _data_acquisition_loop(self) -> None:
        """
        Background loop reading Glove data from bc-edu-sdk buffers at 50Hz
        """
        self._append_log("Acquisition", "Started background Glove data acquisition task.")
        if not self.args.mock:
            return

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
        if not self.streaming or self.calibrating_imu:
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
        if getattr(self, "_is_shutting_down", False):
            event.accept()
            return

        event.ignore()
        asyncio.ensure_future(self._safe_shutdown_async())

    async def _safe_shutdown_async(self) -> None:
        self._is_shutting_down = True
        self.plot_timer.stop()

        try:
            libedu.set_msg_resp_callback(None)
            libedu.set_flex_data_callback(None)
            libedu.set_imu_data_callback(None)
            libedu.set_imu_calibration_data_callback(None)
            libedu.set_mag_data_callback(None)
            libedu.set_mag_calibration_data_callback(None)
        except Exception:
            pass

        if self.connected and not self.args.mock and self.device:
            try:
                await self.device.stop_sensor_data_stream()
                await self.device.stop_stream()
            except Exception:
                pass

        self.close()
        QtWidgets.QApplication.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Glove Acquisition GUI Demo")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic simulated data")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # QTimer trick: ensure Python interpreter runs periodically so signal handlers fire
    _signal_timer = QtCore.QTimer()
    _signal_timer.setInterval(200)
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start()

    win = GloveWindow(args)
    win.show()

    # Allow Ctrl+C to gracefully quit the Qt event loop by closing the window
    signal.signal(signal.SIGINT, lambda *_: win.close())

    with loop:
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
