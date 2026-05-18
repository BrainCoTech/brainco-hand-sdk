"""Timing Test Panel for Revo1/Revo2 workers.

Always shows 3 simultaneous charts:
  Position (°) | Speed (rpm) | Current (mA)

The selected "Control" mode determines which chart overlays the reference
setpoint curve (dashed lighter).  The other two charts show actual only.
"""

import time
import sys
import os
from collections import deque
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QSplitter,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QTextEdit, QComboBox,
    QRadioButton, QButtonGroup,
)
from PySide6.QtCore import QThread, QObject, Qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

from .i18n import tr
from .constants import MOTOR_COLORS, MOTOR_COUNT
from .timing_test_revo2_worker import (
    TimingTestRevo2Worker,
    MODE_ALL_FINGERS, MODE_SINGLE_FINGER,
    SINGLE_FINGER_OPTIONS,
)
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    pg = None
    HAS_PYQTGRAPH = False

MAX_PLOT_POINTS = 500

# Revo1/2 target reference values
_REVO2_CLOSE = 1000
_REVO2_OPEN  = 0

# Fixed color for all REF (setpoint) curves — bright amber, clearly different
# from any finger-coded motor color (teal, red, orange, blue, green)
_REF_COLOR   = (255, 200, 0)    # amber yellow
_REF_ALPHA   = 220              # slight transparency to avoid obscuring ACT

# MIT impedance control formula (for tooltips / chart subtitles)
# τ = Kp·(θ_d − θ) + Kd·(ω_d − ω) + τ_ff
_MIT_FORMULA = "τ = Kp(θₐ−θ) + Kd(ωₐ−ω) + τff"


def _ref_legend_html(var_act: str = 'θ', var_ref: str = 'θₐ',
                    ref_hex: str = '#ffc800', act_hex: str = '#88ddcc') -> str:
    """Return a compact HTML legend string: ACT symbol in motor color, REF in amber."""
    return (
        f"<span style='color:{act_hex}'>▬</span>"
        f"<span style='color:#ccc'> {var_act}</span>&nbsp;&nbsp;"
        f"<span style='color:{ref_hex}'>┈┈</span>"
        f"<span style='color:#ccc'> {var_ref}</span>"
    )


class TimingTestPanel(QWidget):
    """Timing Test Panel.

    - Displays 3 simultaneous charts: Position / Speed / Current.
    - The selected Control mode chart overlays reference setpoint (dashed).
    - Single Finger mode hides inactive curves across all 3 charts.
    """

    def __init__(self):
        super().__init__()
        self.shared_data: Optional['SharedDataManager'] = None
        self.worker: Optional[QObject] = None
        self._thread: Optional[QThread] = None
        self.is_running = False
        self._view_mode = "MIT"

        # Data storage (sized to max device; resized in _update_for_device_type)
        self._num_curves = MOTOR_COUNT
        self.times = deque(maxlen=MAX_PLOT_POINTS)

        def _empty(n):
            return [deque(maxlen=MAX_PLOT_POINTS) for _ in range(n)]

        self.positions     = _empty(MOTOR_COUNT)
        self.speeds        = _empty(MOTOR_COUNT)
        self.currents      = _empty(MOTOR_COUNT)
        self.ref_positions = _empty(MOTOR_COUNT)
        self.ref_speeds    = _empty(MOTOR_COUNT)
        self.ref_currents  = _empty(MOTOR_COUNT)
        self.start_time = None

        # Statistics
        self.packet_count = 0
        self.error_count  = 0
        self._last_packet_times = deque(maxlen=100)
        self._last_latencies    = deque(maxlen=100)

        # Chart curve lists (populated in _setup_revo2/3_chart)
        self.pos_curves     = []
        self.vel_curves     = []
        self.cur_curves     = []
        self.ref_pos_curves = []
        self.ref_vel_curves = []
        self.ref_cur_curves = []
        self._target_lines  = []

        self._setup_ui()
        self.update_texts()

    # ── Device properties ─────────────────────────────────────────────────────

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    @property
    def device_info(self):
        return self.shared_data.device_info if self.shared_data else None

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ── Test mode row ─────────────────────────────────────────────────────
        self.mode_group = QGroupBox()
        mode_layout = QHBoxLayout()

        self.mode_btn_group = QButtonGroup(self)
        self.all_fingers_radio = QRadioButton()
        self.mode_btn_group.addButton(self.all_fingers_radio, MODE_ALL_FINGERS)
        mode_layout.addWidget(self.all_fingers_radio)

        self.single_finger_radio = QRadioButton()
        self.single_finger_radio.setChecked(True)
        self.mode_btn_group.addButton(self.single_finger_radio, MODE_SINGLE_FINGER)
        mode_layout.addWidget(self.single_finger_radio)

        self.finger_label = QLabel()
        mode_layout.addWidget(self.finger_label)

        self.finger_combo = QComboBox()
        for name, idx in SINGLE_FINGER_OPTIONS:
            self.finger_combo.addItem(name, idx)
        self.finger_combo.setCurrentIndex(1)
        self.finger_combo.setMinimumWidth(100)
        mode_layout.addWidget(self.finger_combo)

        mode_layout.addSpacing(20)
        self.view_mode_label = QLabel("Control:")
        mode_layout.addWidget(self.view_mode_label)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("Position", "Position")
        self.view_mode_combo.addItem("Speed", "Speed")
        self.view_mode_combo.addItem("Current", "Current")
        self.view_mode_combo.addItem("MIT", "MIT")
        self.view_mode_combo.setCurrentIndex(3)   # default to MIT mode
        self.view_mode_combo.setMinimumWidth(90)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        mode_layout.addWidget(self.view_mode_combo)

        self.kp_label = QLabel("Kp:")
        self.kp_label.setToolTip(_MIT_FORMULA)
        mode_layout.addWidget(self.kp_label)
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(0.0, 10.0)
        self.kp_spin.setSingleStep(0.5)
        self.kp_spin.setValue(5.0)
        self.kp_spin.setMinimumWidth(60)
        mode_layout.addWidget(self.kp_spin)

        self.kd_label = QLabel("Kd:")
        self.kd_label.setToolTip(_MIT_FORMULA)
        mode_layout.addWidget(self.kd_label)
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.0, 10.0)
        self.kd_spin.setSingleStep(0.1)
        self.kd_spin.setValue(0.5)
        self.kd_spin.setMinimumWidth(60)
        mode_layout.addWidget(self.kd_spin)

        # Start visible since MIT is the default mode
        self.kp_label.setVisible(True)
        self.kp_spin.setVisible(True)
        self.kd_label.setVisible(True)
        self.kd_spin.setVisible(True)

        mode_layout.addSpacing(20)
        self.signal_combo_label = QLabel("Signal:")
        mode_layout.addWidget(self.signal_combo_label)
        self.signal_combo = QComboBox()
        self.signal_combo.addItem("Step", "Step")
        self.signal_combo.addItem("Sine", "Sine")
        self.signal_combo.setCurrentIndex(1)
        self.signal_combo.setMinimumWidth(80)
        mode_layout.addWidget(self.signal_combo)

        mode_layout.addStretch()
        self.mode_group.setLayout(mode_layout)
        layout.addWidget(self.mode_group)

        self.mode_btn_group.buttonClicked.connect(self._on_mode_changed)
        self.finger_combo.currentIndexChanged.connect(self._on_finger_changed)

        # ── Config row ────────────────────────────────────────────────────────
        self.config_group = QGroupBox()
        config_layout = QHBoxLayout()

        self.cycles_label = QLabel()
        config_layout.addWidget(self.cycles_label)
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(1, 100)
        self.cycles_spin.setValue(5)
        config_layout.addWidget(self.cycles_spin)

        self.timeout_label = QLabel()
        config_layout.addWidget(self.timeout_label)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(2)
        config_layout.addWidget(self.timeout_spin)

        config_layout.addSpacing(20)
        self.time_window_label = QLabel()
        config_layout.addWidget(self.time_window_label)
        self.time_window_combo = QComboBox()
        for t in [5, 10, 30, 60]:
            self.time_window_combo.addItem(f"{t}s", t)
        self.time_window_combo.setCurrentIndex(1)
        self.time_window_combo.currentIndexChanged.connect(self._on_time_window_changed)
        config_layout.addWidget(self.time_window_combo)

        config_layout.addStretch()
        self.config_group.setLayout(config_layout)
        layout.addWidget(self.config_group)

        # ── Control buttons + statistics ──────────────────────────────────────
        control_layout = QHBoxLayout()

        self.start_btn = QPushButton()
        self.start_btn.clicked.connect(self._start_test)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.clicked.connect(self._stop_test)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_data)
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        self.stats_group = QGroupBox()
        stats_layout = QHBoxLayout(self.stats_group)
        stats_layout.setSpacing(20)

        def _stat_col(title, color=None):
            col = QVBoxLayout()
            lbl_t = QLabel(title)
            lbl_t.setStyleSheet("color: #888;")
            col.addWidget(lbl_t)
            lbl_v = QLabel("—")
            style = "font-weight: bold; font-size: 14px;"
            if color:
                style += f" color: {color};"
            lbl_v.setStyleSheet(style)
            col.addWidget(lbl_v)
            stats_layout.addLayout(col)
            return lbl_t, lbl_v

        self.read_freq_title, self.read_freq_value = _stat_col("Read Freq",  "#00e676")
        self.freq_title,      self.freq_value      = _stat_col("Chart Freq")
        self.latency_title,   self.latency_value   = _stat_col("Avg Latency")
        self.packets_title,   self.packets_value   = _stat_col("Packets")
        self.errors_title,    self.errors_value    = _stat_col("Errors",     "#dc3545")
        stats_layout.addStretch()
        control_layout.addWidget(self.stats_group)
        layout.addLayout(control_layout)

        # ── 3 Charts (vertical splitter) ──────────────────────────────────────
        if HAS_PYQTGRAPH and pg is not None:
            self._splitter = QSplitter(Qt.Vertical)

            self.pos_plot = self._make_plot("Position (°)", (-10, 120))
            self.vel_plot = self._make_plot("Speed (rpm)",  (-120, 120))
            self.cur_plot = self._make_plot("Current (mA)", (-400, 400))

            self._splitter.addWidget(self.pos_plot)
            self._splitter.addWidget(self.vel_plot)
            self._splitter.addWidget(self.cur_plot)
            self._splitter.setSizes([260, 260, 260])
            layout.addWidget(self._splitter, stretch=1)
        else:
            self.pos_plot = None
            self.vel_plot = None
            self.cur_plot = None
            self.plot_label = QLabel("pyqtgraph not installed — no chart available")
            layout.addWidget(self.plot_label)

        # ── Results text ──────────────────────────────────────────────────────
        self.result_group = QGroupBox()
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(140)
        result_layout.addWidget(self.result_text)
        self.result_group.setLayout(result_layout)
        layout.addWidget(self.result_group)

    def _make_plot(self, ylabel: str, y_range: tuple) -> 'pg.PlotWidget':
        """Create a styled PlotWidget."""
        plot = pg.PlotWidget()
        plot.setBackground('#1a1a2e')
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setLabel('left', ylabel, color='#cccccc')
        plot.setLabel('bottom', 'Time (s)', color='#cccccc')
        plot.setYRange(*y_range)
        plot.setMinimumHeight(180)
        # Ensure Y-axis label is not clipped
        plot.getPlotItem().getAxis('left').setWidth(55)
        # Set axis tick font size for readability
        from PySide6.QtGui import QFont
        axis_font = QFont()
        axis_font.setPointSize(10)
        plot.getPlotItem().getAxis('left').setTickFont(axis_font)
        plot.getPlotItem().getAxis('bottom').setTickFont(axis_font)
        # Set label style (title and axis labels)
        label_style = {'font-size': '12pt', 'color': '#cccccc'}
        plot.getPlotItem().getAxis('left').label.setFont(QFont('', 12))
        plot.getPlotItem().getAxis('bottom').label.setFont(QFont('', 10))
        return plot

    # ── i18n ─────────────────────────────────────────────────────────────────

    def update_texts(self):
        from .i18n import get_i18n, tr
        self.mode_group.setTitle(tr("test_mode"))
        self.all_fingers_radio.setText(tr("mode_all_fingers"))
        self.single_finger_radio.setText(tr("mode_single_finger"))
        self.finger_label.setText(tr("finger_label"))
        self.config_group.setTitle(tr("test_config"))
        self.cycles_label.setText(tr("num_cycles") + ":")
        self.timeout_label.setText(tr("timeout_sec") + ":")
        self.time_window_label.setText(tr("time_window") + ":")
        self.start_btn.setText(tr("btn_start_test"))
        self.stop_btn.setText(tr("btn_stop_test"))
        self.clear_btn.setText(tr("btn_clear"))
        self.stats_group.setTitle(tr("statistics"))
        self.read_freq_title.setText(tr("read_freq"))
        self.freq_title.setText(tr("chart_freq"))
        self.latency_title.setText(tr("avg_latency"))
        self.packets_title.setText(tr("packets"))
        self.errors_title.setText(tr("errors"))
        self.result_group.setTitle(tr("test_results"))
        
        self.view_mode_label.setText(tr("timing_control") + ":")
        self.signal_combo_label.setText(tr("timing_signal") + ":")
        
        self.view_mode_combo.setItemText(0, tr("mode_position"))
        self.view_mode_combo.setItemText(1, tr("mode_speed"))
        self.view_mode_combo.setItemText(2, tr("mode_current"))
        self.view_mode_combo.setItemText(3, tr("mode_mit"))
        
        self.signal_combo.setItemText(0, tr("timing_step"))
        self.signal_combo.setItemText(1, tr("timing_sine"))

    # ── Device setup ──────────────────────────────────────────────────────────

    def set_device(self, device, slave_id, device_info, shared_data=None):
        """Called when a device is connected."""
        self.shared_data = shared_data
        self._update_for_device_type()

    def _update_for_device_type(self):
        """Rebuild finger combo and charts for the connected device."""
        # Block signals so addItem / setCurrentIndex don't trigger
        # _on_finger_changed before the chart curves are created.
        self.finger_combo.blockSignals(True)
        self.finger_combo.clear()

        for name, idx in SINGLE_FINGER_OPTIONS:
            self.finger_combo.addItem(name, idx)
        self.finger_combo.setCurrentIndex(1)
        self._num_curves = MOTOR_COUNT
        self._setup_revo12_chart()

        self.finger_combo.blockSignals(False)
        # Apply correct visibility now that curves exist
        self._on_finger_changed()

        # Reset data storage to match curve count
        n = self._num_curves

        def _empty():
            return [deque(maxlen=MAX_PLOT_POINTS) for _ in range(n)]

        self.times         = deque(maxlen=MAX_PLOT_POINTS)
        self.positions     = _empty()
        self.speeds        = _empty()
        self.currents      = _empty()
        self.ref_positions = _empty()
        self.ref_speeds    = _empty()
        self.ref_currents  = _empty()

    def _setup_revo12_chart(self):
        """Build 3-chart panel for Revo1/2 (6 actual + 6 ref curves per chart)."""
        if not HAS_PYQTGRAPH or pg is None:
            return

        for curves, plot in [
            (self.pos_curves + self.ref_pos_curves, self.pos_plot),
            (self.vel_curves + self.ref_vel_curves, self.vel_plot),
            (self.cur_curves + self.ref_cur_curves, self.cur_plot),
        ]:
            for c in curves:
                try:
                    plot.removeItem(c)
                except Exception:
                    pass
        for line in self._target_lines:
            try:
                self.pos_plot.removeItem(line)
            except Exception:
                pass

        self.pos_curves = []
        self.vel_curves = []
        self.cur_curves = []
        self.ref_pos_curves = []
        self.ref_vel_curves = []
        self.ref_cur_curves = []
        self._target_lines  = []

        DashLine   = pg.QtCore.Qt.DashLine

        self.pos_plot.setYRange(-50, 1050)
        self.pos_plot.setLabel('left', 'Position (0–1000)', color='#cccccc')
        self.pos_plot.setTitle("Position", color='#cccccc', size='12pt')

        self.vel_plot.setYRange(-1050, 1050)
        self.vel_plot.setLabel('left', 'Speed', color='#cccccc')
        self.vel_plot.setTitle("Speed", color='#cccccc', size='12pt')

        self.cur_plot.setYRange(-1050, 1050)
        self.cur_plot.setLabel('left', 'Current', color='#cccccc')
        self.cur_plot.setTitle("Current", color='#cccccc', size='12pt')

        ref_pen_color = (*_REF_COLOR, _REF_ALPHA)
        for plot in [self.pos_plot, self.vel_plot, self.cur_plot]:
            plot_item = plot.getPlotItem()
            if plot_item.legend is None:
                legend = plot.addLegend(offset=(-10, 10))
                legend.anchor((1, 0), (1, 0), offset=(-10, 10))
                legend.setBrush(pg.mkBrush(20, 20, 30, 200))
                legend.setPen(pg.mkPen(color='#555555', width=1))
            else:
                legend = plot_item.legend
                legend.clear()
            act_dummy = pg.PlotDataItem(pen=pg.mkPen(color='#aaaaff', width=3))
            ref_dummy = pg.PlotDataItem(pen=pg.mkPen(color=ref_pen_color, width=2, style=DashLine))
            legend.addItem(act_dummy, "ACT")
            legend.addItem(ref_dummy, "REF")

        self._target_lines.append(
            self.pos_plot.addLine(y=_REVO2_CLOSE,
                pen=pg.mkPen('g', style=DashLine, width=1)))
        self._target_lines.append(
            self.pos_plot.addLine(y=500,
                pen=pg.mkPen('r', style=DashLine, width=1)))
        self._target_lines.append(
            self.pos_plot.addLine(y=_REVO2_OPEN,
                pen=pg.mkPen((100, 100, 255), style=DashLine, width=1)))


        for color in MOTOR_COLORS:
            solid = pg.mkPen(color=color,         width=2)
            dash  = pg.mkPen(color=ref_pen_color, width=1.5, style=DashLine)

            self.pos_curves.append(self.pos_plot.plot([], [], pen=solid))
            self.vel_curves.append(self.vel_plot.plot([], [], pen=solid))
            self.cur_curves.append(self.cur_plot.plot([], [], pen=solid))

            self.ref_pos_curves.append(self.pos_plot.plot([], [], pen=dash))
            self.ref_vel_curves.append(self.vel_plot.plot([], [], pen=dash))
            self.ref_cur_curves.append(self.cur_plot.plot([], [], pen=dash))

        for rc in self.ref_pos_curves + self.ref_vel_curves + self.ref_cur_curves:
            rc.setVisible(False)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_mode_changed(self, button):
        is_single = self.mode_btn_group.checkedId() == MODE_SINGLE_FINGER
        self.finger_label.setEnabled(is_single)
        self.finger_combo.setEnabled(is_single)
        if is_single:
            self._on_finger_changed()
        else:
            self._restore_all_curves()

    def _on_finger_changed(self, _index=None):
        """Update curve visibility when finger / joint selection changes."""
        if self.mode_btn_group.checkedId() != MODE_SINGLE_FINGER:
            return
        self._set_active_curves(self._resolve_active_joints())

    def _on_view_mode_changed(self, index: int):
        mode_str = self.view_mode_combo.itemData(index)
        self._view_mode = mode_str
        is_mit = (mode_str == "MIT")
        self.kp_label.setVisible(is_mit)
        self.kp_spin.setVisible(is_mit)
        self.kd_label.setVisible(is_mit)
        self.kd_spin.setVisible(is_mit)
        self._sync_ref_visibility()

    def _on_time_window_changed(self, _index):
        self._update_plot()

    # ── Curve visibility ──────────────────────────────────────────────────────

    def _resolve_active_joints(self) -> list:
        """Return motor IDs for the current Single Finger selection."""
        finger_index = self.finger_combo.currentData()
        if isinstance(finger_index, int):
            return [finger_index]
        return list(range(self._num_curves))

    def _set_active_curves(self, active_indices: list):
        """Show only active joints in all 3 actual charts; update ref overlay."""
        active_set = set(active_indices)
        for curves in (self.pos_curves, self.vel_curves, self.cur_curves):
            for i, c in enumerate(curves):
                c.setVisible(i in active_set)
        self._sync_ref_visibility()

    def _restore_all_curves(self):
        """Show all actual curves; update ref overlay."""
        for curves in (self.pos_curves, self.vel_curves, self.cur_curves):
            for c in curves:
                c.setVisible(True)
        self._sync_ref_visibility()

    def _sync_ref_visibility(self):
        """Show ref curves only in the active Control mode chart, active joints."""
        if self.mode_btn_group.checkedId() == MODE_SINGLE_FINGER:
            active_set = set(self._resolve_active_joints())
        else:
            active_set = set(range(self._num_curves))

        mode_str = self._view_mode
        for i, (rpc, rvc, rcc) in enumerate(zip(
                self.ref_pos_curves, self.ref_vel_curves, self.ref_cur_curves)):
            in_active = i in active_set
            rpc.setVisible(in_active and mode_str in ("Position", "MIT"))
            rvc.setVisible(in_active and mode_str in ("Speed", "MIT"))
            rcc.setVisible(in_active and mode_str == "Current")

    # ── Chart updates ─────────────────────────────────────────────────────────

    def _update_plot(self):
        if not HAS_PYQTGRAPH or self.pos_plot is None:
            return
        times = list(self.times)
        if not times:
            for curves in (self.pos_curves, self.vel_curves, self.cur_curves,
                           self.ref_pos_curves, self.ref_vel_curves, self.ref_cur_curves):
                for c in curves:
                    c.setData([], [])
            return

        for i in range(self._num_curves):
            if i < len(self.pos_curves):
                self.pos_curves[i].setData(times, list(self.positions[i]))
            if i < len(self.vel_curves):
                self.vel_curves[i].setData(times, list(self.speeds[i]))
            if i < len(self.cur_curves):
                self.cur_curves[i].setData(times, list(self.currents[i]))
            # ref_point signal arrives one frame later than data_point (Qt queued
            # cross-thread delivery order).  Trim times to ref length to avoid
            # "X and Y arrays must be the same shape" crash.
            if i < len(self.ref_pos_curves):
                rp = list(self.ref_positions[i])
                self.ref_pos_curves[i].setData(times[:len(rp)], rp)
            if i < len(self.ref_vel_curves):
                rv = list(self.ref_speeds[i])
                self.ref_vel_curves[i].setData(times[:len(rv)], rv)
            if i < len(self.ref_cur_curves):
                rc = list(self.ref_currents[i])
                self.ref_cur_curves[i].setData(times[:len(rc)], rc)

        # Sync X axis across all 3 charts (disable auto-range first to prevent override)
        if len(times) > 1:
            time_window = self.time_window_combo.currentData() or 10
            x_max = times[-1] + 0.5
            x_min = max(0.0, x_max - time_window)
            for plot in (self.pos_plot, self.vel_plot, self.cur_plot):
                plot.disableAutoRange(axis='x')
                plot.setXRange(x_min, x_max, padding=0)

    def _add_data(self, positions, speeds, currents):
        """Slot for worker.data_point — actual motor feedback (~50 Hz)."""
        if self.start_time is None:
            self.start_time = time.time()
        t = time.time() - self.start_time
        self.times.append(t)
        for i in range(min(self._num_curves, len(positions))):
            self.positions[i].append(positions[i])
        for i in range(min(self._num_curves, len(speeds))):
            self.speeds[i].append(speeds[i])
        for i in range(min(self._num_curves, len(currents))):
            self.currents[i].append(currents[i])
        self._record_packet()
        self._update_chart_freq()
        self._update_plot()

    def _add_ref_data(self, ref_positions, ref_speeds, ref_currents):
        """Slot for worker.ref_point — reference setpoint, emitted alongside data_point."""
        for i in range(min(self._num_curves, len(ref_positions))):
            self.ref_positions[i].append(ref_positions[i])
        for i in range(min(self._num_curves, len(ref_speeds))):
            self.ref_speeds[i].append(ref_speeds[i])
        for i in range(min(self._num_curves, len(ref_currents))):
            self.ref_currents[i].append(ref_currents[i])
        # _update_plot() is triggered by _add_data (emitted simultaneously)

    # ── Statistics ────────────────────────────────────────────────────────────

    def _on_stats_update(self, total_read_count, elapsed):
        if elapsed > 0:
            self.read_freq_value.setText(f"{total_read_count / elapsed:.1f} Hz")
            avg_ms = (elapsed / total_read_count * 1000) if total_read_count > 0 else 0
            self.latency_value.setText(f"{avg_ms:.1f} ms")
            self.packets_value.setText(str(total_read_count))

    def _update_chart_freq(self):
        freq = 0.0
        if len(self._last_packet_times) >= 2:
            ts  = list(self._last_packet_times)
            dur = ts[-1] - ts[0]
            if dur > 0:
                freq = (len(ts) - 1) / dur
        self.freq_value.setText(f"{freq:.1f} Hz")

    def _record_packet(self, latency: float = 0):
        self.packet_count += 1
        self._last_packet_times.append(time.time())
        if latency > 0:
            self._last_latencies.append(latency)

    def _record_error(self):
        self.error_count += 1

    # ── Data management ───────────────────────────────────────────────────────

    def _clear_data(self):
        self.times.clear()
        self.start_time = None
        self.packet_count = 0
        self.error_count  = 0
        self._last_packet_times.clear()
        self._last_latencies.clear()
        for buf_list in (self.positions, self.speeds, self.currents,
                         self.ref_positions, self.ref_speeds, self.ref_currents):
            for b in buf_list:
                b.clear()
        for curves in (self.pos_curves, self.vel_curves, self.cur_curves,
                       self.ref_pos_curves, self.ref_vel_curves, self.ref_cur_curves):
            for c in curves:
                c.setData([], [])
        # Reset view to auto-range so next test starts fresh
        if HAS_PYQTGRAPH and self.pos_plot is not None:
            for plot in (self.pos_plot, self.vel_plot, self.cur_plot):
                plot.enableAutoRange(axis='x')

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, message):
        self.result_text.append(message)

    # ── Test control ──────────────────────────────────────────────────────────

    def _start_test(self):
        if not self.device:
            self._log(tr("error_no_device"))
            return

        self.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._clear_data()

        test_mode    = self.mode_btn_group.checkedId()
        finger_index = (self.finger_combo.currentData()
                        if test_mode == MODE_SINGLE_FINGER else 0)

        if test_mode == MODE_SINGLE_FINGER:
            self._set_active_curves(self._resolve_active_joints())
        else:
            self._restore_all_curves()

        signal_type = self.signal_combo.currentText()
        WorkerClass = TimingTestRevo2Worker

        self._thread = QThread()
        worker_kwargs = dict(
            view_mode=self._view_mode,
            signal_type=signal_type,
        )
        self.worker  = WorkerClass(
            self.device,
            self.slave_id,
            self.cycles_spin.value(),
            self.timeout_spin.value(),
            test_mode,
            finger_index,
            self.shared_data,
            **worker_kwargs,
        )
        self.worker.moveToThread(self._thread)

        self._thread.started.connect(self.worker.run)
        self.worker.log_message.connect(self._log)
        self.worker.data_point.connect(self._add_data)
        self.worker.stats_update.connect(self._on_stats_update)
        self.worker.finished.connect(self._on_test_finished)
        self.worker.finished.connect(self._thread.quit)

        if hasattr(self.worker, 'ref_point'):
            self.worker.ref_point.connect(self._add_ref_data)

        self._thread.start()

    def _stop_test(self):
        if self.worker:
            self.worker.stop()
        self.is_running = False

    def _on_test_finished(self):
        self.is_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # Curve visibility kept as-is so the result chart stays readable
