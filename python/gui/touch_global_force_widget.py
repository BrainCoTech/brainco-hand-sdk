"""Global Force Widget for Revo1/Revo2 Touch

Displays global 6D force/torque calculated from all finger sensors.

Layout (optimized for horizontal space):
┌─────────────────────────────────────────────────────────────────┐
│  🌐 Global Force & Torque  ·  13 sensors (Revo1)               │
├───────────────┬──────────────┬──────────────────────────────────┤
│  [Force       │  [Torque     │  Fx ±xx  Fy ±xx  Fz ±xx        │
│   Compass]    │   Compass]   │  Mx ±xx  My ±xx  Mz ±xx        │
│   Fx Fy Fz    │   Mx My Mz   │  |F| xx  |T| xx  Sensors n/N   │
├───────────────┴──────────────┴──────────────────────────────────┤
│  [Force6DChart - 6 curves time series]                          │
└─────────────────────────────────────────────────────────────────┘
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QGridLayout, QFrame
)
from PySide6.QtCore import Qt

from .styles import COLORS
from .touch_global_force import GlobalForceCalculator

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    pg = None
    HAS_PYQTGRAPH = False

try:
    from .touch_chart_force6d import Force6DChart
    HAS_FORCE6D_CHART = True
except ImportError:
    HAS_FORCE6D_CHART = False


class CompactCompass(QWidget):
    """Compact force or torque vector compass (single 2D plot)"""

    def __init__(self, title: str, color: tuple, xy_range: float = 30.0,
                 ref_circles: list = None, unit: str = "N"):
        super().__init__()
        self.color = color
        self.xy_range = xy_range
        self.unit = unit
        self._setup_ui(title, ref_circles or [])

    def _setup_ui(self, title, ref_circles):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        if not HAS_PYQTGRAPH or pg is None:
            layout.addWidget(QLabel("pyqtgraph required"))
            return

        self.plot = pg.PlotWidget()
        self.plot.setBackground('#1a1a2e')
        self.plot.setAspectLocked(True)
        self.plot.setXRange(-self.xy_range, self.xy_range)
        self.plot.setYRange(-self.xy_range, self.xy_range)
        self.plot.hideAxis('bottom')
        self.plot.hideAxis('left')
        self.plot.setTitle(title, color='gray', size='8pt')

        # Reference circles/boxes
        for r_val in ref_circles:
            circle = pg.QtWidgets.QGraphicsEllipseItem(-r_val, -r_val, r_val * 2, r_val * 2)
            circle.setPen(pg.mkPen('#444', width=1, style=Qt.DashLine))
            self.plot.addItem(circle)

        # Axes
        self.plot.addLine(x=0, pen=pg.mkPen('#444', width=1))
        self.plot.addLine(y=0, pen=pg.mkPen('#444', width=1))

        r, g, b = self.color
        # Vector arrow
        self.arrow_line = self.plot.plot([0], [0], pen=pg.mkPen('w', width=3))
        self.arrow_head = pg.ScatterPlotItem(size=10, brush=pg.mkBrush('w'))
        self.plot.addItem(self.arrow_head)

        # Magnitude bubble
        self.bubble = pg.ScatterPlotItem(
            size=10, pen=pg.mkPen('w', width=1),
            brush=pg.mkBrush(r, g, b, 120)
        )
        self.plot.addItem(self.bubble)

        layout.addWidget(self.plot, 1)

    def update(self, x: float, y: float, z_mag: float = 0.0):
        """Update compass: (x,y) as arrow, z as bubble size"""
        if not HAS_PYQTGRAPH:
            return
        # Arrow
        self.arrow_line.setData([0, x], [0, y])
        self.arrow_head.setData([x], [y])
        # Bubble from z magnitude
        bubble_size = max(5.0, min(80.0, (abs(z_mag) / self.xy_range) * 60.0 + 5.0))
        self.bubble.setData([0], [0], size=bubble_size)

    def clear(self):
        if HAS_PYQTGRAPH:
            self.arrow_line.setData([], [])
            self.arrow_head.setData([], [])
            self.bubble.setData([], [])


class GlobalForceWidget(QWidget):
    """Widget displaying global 6D force/torque from Revo1/Revo2 Touch"""

    def __init__(self):
        super().__init__()
        self.is_revo2 = False
        self.calculator = GlobalForceCalculator()
        self.current_force6d = np.zeros(6)
        self._setup_ui()

    def set_hardware_type(self, hw_type):
        """Configure for Revo1 or Revo2 touch hardware"""
        try:
            from common_imports import uses_revo2_touch_api
            self.is_revo2 = uses_revo2_touch_api(hw_type)
        except Exception:
            self.is_revo2 = False

        self.calculator.is_revo2 = self.is_revo2
        if self.is_revo2:
            self.info_label.setText("5 output groups (Revo2)")
            self.active_sensors_label.setText("0/5")
        else:
            self.info_label.setText("13 sensors (Revo1)")
            self.active_sensors_label.setText("0/13")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("🌐 Global Force & Torque")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #5D9CEC;")
        header.addWidget(title)
        self.info_label = QLabel("13 sensors (Revo1)")
        self.info_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; font-style: italic;"
        )
        header.addWidget(self.info_label)
        header.addStretch()
        layout.addLayout(header)

        # ── Top panel: Compasses (left) + Values (right) ──
        top_frame = QFrame()
        top_frame.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['bg_card']}; border-radius: 6px; }}"
        )
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.setSpacing(4)

        # Force compass (Fx,Fy arrow + Fz bubble)
        self.force_compass = CompactCompass(
            "3D Force (N)", (93, 156, 236),
            xy_range=30.0, ref_circles=[10, 20, 30]
        )
        top_layout.addWidget(self.force_compass, 1)

        # Torque compass (Mx,My arrow + Mz bubble)
        self.torque_compass = CompactCompass(
            "Torque (N·m)", (230, 126, 34),
            xy_range=2.5, ref_circles=[0.5, 1.0, 2.0]
        )
        top_layout.addWidget(self.torque_compass, 1)

        # Values panel (compact grid)
        values_widget = QWidget()
        vgrid = QGridLayout(values_widget)
        vgrid.setContentsMargins(6, 4, 6, 4)
        vgrid.setSpacing(3)

        self.force_labels = {}

        # Row 0: Force (Fx, Fy, Fz)
        force_items = [('Fx', '#e74c3c'), ('Fy', '#27ae60'), ('Fz', '#3498db')]
        for col, (name, color) in enumerate(force_items):
            n = QLabel(name)
            n.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")
            v = QLabel("0.00")
            v.setStyleSheet(
                "font-size: 14px; font-family: 'Courier New'; color: #ecf0f1;"
            )
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vgrid.addWidget(n, 0, col * 2)
            vgrid.addWidget(v, 0, col * 2 + 1)
            self.force_labels[name] = v

        # Row 1: Torque (Mx, My, Mz)
        torque_items = [('Mx', '#e67e22'), ('My', '#9b59b6'), ('Mz', '#1abc9c')]
        for col, (name, color) in enumerate(torque_items):
            n = QLabel(name)
            n.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")
            v = QLabel("0.000")
            v.setStyleSheet(
                "font-size: 12px; font-family: 'Courier New'; "
                f"color: {COLORS.get('text_muted', '#aaa')};"
            )
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vgrid.addWidget(n, 1, col * 2)
            vgrid.addWidget(v, 1, col * 2 + 1)
            self.force_labels[name] = v

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {COLORS.get('border', '#444')};")
        vgrid.addWidget(sep, 2, 0, 1, 6)

        # Row 3: Stats
        stat_s = f"font-size: 12px; font-weight: bold; color: #ecf0f1;"
        lbl_s = f"font-size: 10px; color: {COLORS.get('text_muted', '#888')};"

        vgrid.addWidget(self._lbl("|F|:", lbl_s), 3, 0)
        self.total_force_label = self._lbl("--", stat_s)
        vgrid.addWidget(self.total_force_label, 3, 1)

        vgrid.addWidget(self._lbl("|T|:", lbl_s), 3, 2)
        self.total_torque_label = self._lbl("--", stat_s)
        vgrid.addWidget(self.total_torque_label, 3, 3)

        vgrid.addWidget(self._lbl("Sensors:", lbl_s), 3, 4)
        self.active_sensors_label = self._lbl("0/13", stat_s)
        vgrid.addWidget(self.active_sensors_label, 3, 5)

        # Row 4: Max
        vgrid.addWidget(self._lbl("Max Fz:", lbl_s), 4, 0)
        self.max_normal_label = self._lbl("--", stat_s)
        vgrid.addWidget(self.max_normal_label, 4, 1)

        vgrid.addWidget(self._lbl("Max Ft:", lbl_s), 4, 2)
        self.max_tangential_label = self._lbl("--", stat_s)
        vgrid.addWidget(self.max_tangential_label, 4, 3)

        for c in range(1, 6, 2):
            vgrid.setColumnStretch(c, 1)

        top_layout.addWidget(values_widget, 2)

        # Top panel fixed height to leave room for chart
        top_frame.setMaximumHeight(220)
        layout.addWidget(top_frame)

        # ── Bottom: Force6D time-series chart ──
        if HAS_FORCE6D_CHART:
            try:
                self.force_chart = Force6DChart(
                    title="Global 6D Force/Torque",
                    components=6,
                    show_values=False,
                    accent_color=(93, 156, 236),
                )
                layout.addWidget(self.force_chart, 1)
            except Exception:
                self.force_chart = None
        else:
            self.force_chart = None

    @staticmethod
    def _lbl(text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        return lbl

    def update_data(self, touch_data):
        """Update display with new touch data"""
        if touch_data is None:
            return

        try:
            summary = self.calculator.calculate_summary(touch_data)
            force6d = summary['force6d']
            self.current_force6d = force6d

            # Update force/torque labels
            for i, name in enumerate(['Fx', 'Fy', 'Fz']):
                self.force_labels[name].setText(f"{force6d[i]:+.2f}")
            for i, name in enumerate(['Mx', 'My', 'Mz']):
                self.force_labels[name].setText(f"{force6d[i+3]:+.4f}")

            # Update stats
            self.total_force_label.setText(f"{summary['total_force']:.2f} N")
            self.total_torque_label.setText(f"{summary['total_torque']:.4f} N·m")
            total_sensors = 5 if self.is_revo2 else 13
            self.active_sensors_label.setText(f"{summary['active_sensors']}/{total_sensors}")
            self.max_normal_label.setText(f"{summary['max_normal_force']:.2f} N")
            self.max_tangential_label.setText(f"{summary['max_tangential_force']:.2f} N")

            # Update compasses
            self.force_compass.update(force6d[0], force6d[1], force6d[2])
            self.torque_compass.update(force6d[3], force6d[4], force6d[5])

            # Update time-series chart
            if self.force_chart:
                self.force_chart.add_data_array(force6d)

        except Exception as e:
            from common_imports import logger
            logger.error(f"Error updating global force widget: {e}")

    def clear(self):
        """Clear all data"""
        self.current_force6d = np.zeros(6)
        for name in ['Fx', 'Fy', 'Fz']:
            self.force_labels[name].setText("0.00")
        for name in ['Mx', 'My', 'Mz']:
            self.force_labels[name].setText("0.000")
        self.total_force_label.setText("0.00 N")
        self.total_torque_label.setText("0.000 N·m")
        self.active_sensors_label.setText("0/13")
        self.max_normal_label.setText("0.00 N")
        self.max_tangential_label.setText("0.00 N")
        self.force_compass.clear()
        self.torque_compass.clear()
        if self.force_chart:
            self.force_chart.clear()
