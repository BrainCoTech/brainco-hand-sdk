"""Force Touch Panel - For Revo2 ArrayPressure devices

Displays 3D force (Fx, Fy, Fz) and 2D torque (Mx, My) data for 5 fingers.
Data source: registers 8100-8124, int16 × 100 scaling.

Tabs:
- Overview: Fz summary curves + status cards
- Force/Torque: Per-finger Fx/Fy/Fz/Mx/My real-time curves with values
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QGridLayout
)
from PySide6.QtCore import Qt

from .touch_common import (
    SummaryChart, HeatmapChart, build_status_cards,
    run_async, HAS_PYQTGRAPH, pg, logger, COLORS
)


# 5 fingers
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
FINGER_COLORS = [
    (255, 100, 100),   # Thumb - Red
    (100, 255, 100),   # Index - Green
    (100, 100, 255),   # Middle - Blue
    (255, 255, 100),   # Ring - Yellow
    (255, 100, 255),   # Pinky - Magenta
]

# Force/torque parameter names and colors
PARAM_NAMES = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]
PARAM_COLORS = [
    (255, 80, 80),     # Fx - Red
    (80, 200, 80),     # Fy - Green
    (80, 130, 255),    # Fz - Blue
    (255, 180, 50),    # Mx - Orange
    (200, 80, 255),    # My - Purple
    (26, 188, 156),    # Mz - Teal
]

# Data ranges
FORCE_RANGE = (-30, 30)     # N
FZ_RANGE = (0, 30)          # N (unsigned)
TORQUE_RANGE = (-2.0, 2.0)    # N·m


class ForceTorqueFingerChart(QWidget):
    """Single finger 2D Vector Compass display for 3D Force & 2D Torque"""

    def __init__(self, finger_name: str, color: tuple):
        super().__init__()
        self.finger_name = finger_name
        self.finger_color = color
        self.current_values = [0.0] * 5
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Header
        r, g, b = self.finger_color
        header = QLabel(f"👆 {self.finger_name} Vector")
        header.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: rgb({r},{g},{b}); "
            f"background-color: #1a1a2e; border-radius: 4px; padding: 4px 8px;"
        )
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        if HAS_PYQTGRAPH and pg is not None:
            # --- 1. Force Vector (Fx, Fy, Fz) Compass ---
            self.force_compass = pg.PlotWidget()
            self.force_compass.setBackground('#1a1a2e')
            self.force_compass.setAspectLocked(True)
            self.force_compass.setXRange(-30, 30)
            self.force_compass.setYRange(-30, 30)
            self.force_compass.hideAxis('bottom')
            self.force_compass.hideAxis('left')
            self.force_compass.setTitle("3D Force Vector (N)", color='gray', size='8pt')

            # Reference circles at 10N, 20N, 30N
            for r_val in [10, 20, 30]:
                circle = pg.QtWidgets.QGraphicsEllipseItem(-r_val, -r_val, r_val * 2, r_val * 2)
                circle.setPen(pg.mkPen('#444', width=1, style=Qt.DashLine))
                self.force_compass.addItem(circle)
            # Axes
            self.force_compass.addLine(x=0, pen=pg.mkPen('#444', width=1))
            self.force_compass.addLine(y=0, pen=pg.mkPen('#444', width=1))

            # Fz Bubble (Size = Normal force)
            self.fz_bubble = pg.ScatterPlotItem(size=10, pen=pg.mkPen('w', width=1), brush=pg.mkBrush(r, g, b, 120))
            self.force_compass.addItem(self.fz_bubble)

            # Fx, Fy Arrow (Line + Head)
            self.fxy_line = self.force_compass.plot([0], [0], pen=pg.mkPen('w', width=3))
            self.fxy_head = pg.ScatterPlotItem(size=10, brush=pg.mkBrush('w'))
            self.force_compass.addItem(self.fxy_head)

            layout.addWidget(self.force_compass, stretch=5)

            # --- 2. Force Values Panel (single row: Fx Fy Fz) ---
            force_vals_frame = QFrame()
            force_vals_frame.setStyleSheet("background-color: #1a1a2e; border-radius: 4px; padding: 2px;")
            force_vals_layout = QHBoxLayout(force_vals_frame)
            force_vals_layout.setContentsMargins(2, 1, 2, 1)
            force_vals_layout.setSpacing(1)

            self.value_labels = {}
            # Fx, Fy, Fz (Indices 0, 1, 2)
            for i in range(3):
                name = PARAM_NAMES[i]
                r_c, g_c, b_c = PARAM_COLORS[i]

                name_lbl = QLabel(f"{name}:")
                name_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: rgb({r_c},{g_c},{b_c});")
                val_lbl = QLabel("0.00")
                val_lbl.setStyleSheet("font-size: 10px; font-family: 'Courier New'; color: #eee;")
                val_lbl.setAlignment(Qt.AlignLeft)

                force_vals_layout.addWidget(name_lbl)
                force_vals_layout.addWidget(val_lbl)
                if i < 2:  # Add small spacing between pairs, not after last
                    force_vals_layout.addSpacing(4)
                self.value_labels[name] = val_lbl
            force_vals_layout.addStretch()

            layout.addWidget(force_vals_frame)

            # --- 3. Torque Vector (Mx, My) Compass ---
            self.torque_compass = pg.PlotWidget()
            self.torque_compass.setBackground('#1a1a2e')
            self.torque_compass.setAspectLocked(True)
            self.torque_compass.setXRange(-2.5, 2.5)
            self.torque_compass.setYRange(-2.5, 2.5)
            self.torque_compass.hideAxis('bottom')
            self.torque_compass.hideAxis('left')
            self.torque_compass.setTitle("Torque Twist (N·m)", color='gray', size='8pt')

            # Crosshair & reference circles
            self.torque_compass.addLine(x=0, pen=pg.mkPen('#444', width=1, style=Qt.DashLine))
            self.torque_compass.addLine(y=0, pen=pg.mkPen('#444', width=1, style=Qt.DashLine))
            for r_val in [0.5, 1.0, 2.0]:
                circle = pg.QtWidgets.QGraphicsEllipseItem(-r_val, -r_val, r_val * 2, r_val * 2)
                circle.setPen(pg.mkPen('#444', width=1, style=Qt.DashLine))
                self.torque_compass.addItem(circle)

            # Torque offset dot
            self.torque_dot = pg.ScatterPlotItem(size=12, pen=pg.mkPen('w', width=1), brush=pg.mkBrush(255, 180, 50, 220))
            self.torque_compass.addItem(self.torque_dot)
            layout.addWidget(self.torque_compass, stretch=4)

            # --- 4. Torque Values Panel (single row: Mx My Mz) ---
            torque_vals_frame = QFrame()
            torque_vals_frame.setStyleSheet("background-color: #1a1a2e; border-radius: 4px; padding: 2px;")
            torque_vals_layout = QHBoxLayout(torque_vals_frame)
            torque_vals_layout.setContentsMargins(2, 1, 2, 1)
            torque_vals_layout.setSpacing(1)

            # Mx, My, Mz (Indices 3, 4, 5)
            for i in range(3, 6):
                name = PARAM_NAMES[i]
                r_c, g_c, b_c = PARAM_COLORS[i]

                name_lbl = QLabel(f"{name}:")
                name_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: rgb({r_c},{g_c},{b_c});")
                val_lbl = QLabel("0.00")
                val_lbl.setStyleSheet("font-size: 10px; font-family: 'Courier New'; color: #eee;")
                val_lbl.setAlignment(Qt.AlignLeft)

                torque_vals_layout.addWidget(name_lbl)
                torque_vals_layout.addWidget(val_lbl)
                if i < 5:
                    torque_vals_layout.addSpacing(4)
                self.value_labels[name] = val_lbl
            torque_vals_layout.addStretch()

            layout.addWidget(torque_vals_frame)

        else:
            layout.addWidget(QLabel("pyqtgraph required"))

    def add_data(self, fx: float, fy: float, fz: float, mx: float, my: float, mz: float = 0.0):
        """Update 2D Vector displays and numeric labels"""
        self.current_values = [fx, fy, fz, mx, my, mz]

        if HAS_PYQTGRAPH and pg is not None:
            # Force Compass Update
            # Fz (Normal force) -> Bubble diameter (min 5, max bounds based on Fz)
            bubble_size = max(5.0, min(100.0, (abs(fz) / 30.0) * 80.0 + 5.0))
            self.fz_bubble.setData([0], [0], size=bubble_size)

            # Fx, Fy -> Shear vector pointing to (Fx, Fy)
            self.fxy_line.setData([0, fx], [0, fy])
            self.fxy_head.setData([fx], [fy])

            # Torque Compass Update
            # Plot (Mx, My) as a dot on the grid
            self.torque_dot.setData([mx], [my])

        # Numeric Update
        for i, name in enumerate(PARAM_NAMES):
            unit = "N" if i < 3 else "N·m"
            self.value_labels[name].setText(f"{self.current_values[i]:+.2f} {unit}")

    def clear(self):
        self.current_values = [0.0] * 6
        if HAS_PYQTGRAPH and pg is not None:
            self.fz_bubble.setData([], [])
            self.fxy_line.setData([], [])
            self.fxy_head.setData([], [])
            self.torque_dot.setData([], [])
        for name in PARAM_NAMES:
            self.value_labels[name].setText("0.00")


class ForceTouchSubPanel(QWidget):
    """Force Touch Panel for ArrayPressure devices.

    Tabs:
    - Overview: Fz summary for 5 fingers + status cards
    - Force/Torque: 5 finger charts side by side
    """

    def __init__(self):
        super().__init__()
        self.finger_charts = []
        self.sensor_cards = []
        self.sensor_bars = []
        self.sensor_labels = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tabs = QTabWidget()

        # --- Tab 1: Overview ---
        overview_widget = QWidget()
        overview_layout = QGridLayout(overview_widget)
        overview_layout.setSpacing(8)

        # Summary chart (left): Fz curves for all 5 fingers
        self.summary_chart = SummaryChart(
            "Fz Force Summary (N)", (-5, 35),
            sensor_names=FINGER_NAMES,
            sensor_colors=FINGER_COLORS,
            y_label="N"
        )
        overview_layout.addWidget(self.summary_chart, 0, 0, 2, 1)

        # Status cards (right)
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setSpacing(4)

        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            status_layout, FINGER_NAMES, FINGER_COLORS
        )

        overview_layout.addWidget(status_widget, 0, 1, 2, 1)
        overview_layout.setColumnStretch(0, 3)
        overview_layout.setColumnStretch(1, 1)

        self.tabs.addTab(overview_widget, "📊 Overview")

        # --- Tab 2: Force/Torque Detail ---
        ft_widget = QWidget()
        ft_layout = QHBoxLayout(ft_widget)
        ft_layout.setContentsMargins(4, 4, 4, 4)
        ft_layout.setSpacing(4)

        self.finger_charts = []
        for name, color in zip(FINGER_NAMES, FINGER_COLORS):
            chart = ForceTorqueFingerChart(name, color)
            self.finger_charts.append(chart)
            ft_layout.addWidget(chart, 1)

        self.tabs.addTab(ft_widget, "💪 Force/Torque")

        layout.addWidget(self.tabs, 1)

    def update_data(self, raw_data: list):
        """Update with raw register data (25 int16 values, ×100 scaled).

        raw_data: [Fx,Fy,Fz,Mx,My] × 5 fingers (Thumb,Index,Middle,Ring,Pinky)
        """
        if not raw_data or len(raw_data) < 25:
            return

        fz_values = []  # For summary chart

        for finger_idx in range(5):
            base = finger_idx * 5
            # Convert from u16 (unsigned) to int16 (signed), then scale ÷100
            # Raw values come as u16 from Rust; values >32767 represent negative int16
            # Robust fallback: handle if raw_data contains negative python ints directly
            values = [x & 0xFFFF for x in raw_data[base:base + 5]]
            raw_slice = np.array(values, dtype=np.uint16).view(np.int16)
            fx = float(raw_slice[0]) / 100.0
            fy = float(raw_slice[1]) / 100.0
            fz = float(raw_slice[2]) / 100.0
            mx = float(raw_slice[3]) / 100.0
            my = float(raw_slice[4]) / 100.0

            fz_values.append(fz)

            # Update finger chart
            if finger_idx < len(self.finger_charts):
                self.finger_charts[finger_idx].add_data(fx, fy, fz, mx, my)

            # Update status card
            if finger_idx < len(self.sensor_bars):
                # Scale Fz to progress bar (0-5000 range, map 0-30N to 0-5000)
                bar_val = int(abs(fz) * 5000 / 30)
                self.sensor_bars[finger_idx].setValue(min(bar_val, 5000))
                self.sensor_labels[finger_idx].setText(f"{fz:.1f} N")

        # Update summary chart with Fz values
        self.summary_chart.add_data(fz_values)

    def clear(self):
        self.summary_chart.clear()
        for chart in self.finger_charts:
            chart.clear()
