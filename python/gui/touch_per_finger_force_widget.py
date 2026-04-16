"""Per-Finger 6D Force Widget for Capacitive Touch

Displays per-finger 6D force/torque using ForceTorqueFingerChart (vector compass).
Reuses the same chart component as the ArrayPressure Force panel.

For Revo1: Each finger has 2-3 sensors → meaningful 6D force/torque
For Revo2: Each finger has 1 sensor → 3D force only (Fx, Fy from tangential direction)
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QScrollArea
)
from PySide6.QtCore import Qt

from .styles import COLORS
from .constants import TOUCH_COLORS, TOUCH_NAMES_EN, TOUCH_SENSOR_CONFIG
from .touch_panel_force import ForceTorqueFingerChart

try:
    from .touch_chart_force6d import Force6DChart
    HAS_FORCE6D_CHART = True
except ImportError:
    HAS_FORCE6D_CHART = False


# Revo1 sensor counts per finger (from TOUCH_SENSOR_CONFIG)
REVO1_SENSOR_COUNTS = {name: TOUCH_SENSOR_CONFIG[name][0] for name in TOUCH_NAMES_EN}
REVO1_TOTAL_SENSORS = sum(REVO1_SENSOR_COUNTS.values())  # 13

# Revo2: all fingers have 1 sensor
REVO2_SENSOR_COUNTS = {name: 1 for name in TOUCH_NAMES_EN}
REVO2_TOTAL_SENSORS = 5

# Colors matching ForceTorqueFingerChart convention
FINGER_COLORS_FORCE = [
    (255, 100, 100),   # Thumb - Red
    (100, 255, 100),   # Index - Green
    (100, 100, 255),   # Middle - Blue
    (255, 255, 100),   # Ring - Yellow
    (255, 100, 255),   # Pinky - Magenta
]


class PerFingerForceWidget(QWidget):
    """Widget showing per-finger force using ForceTorqueFingerChart (compass).

    Adapts display based on hardware type:
    - Revo1: Shows full 6D force/torque (2-3 sensors per finger)
    - Revo2: Shows 3D force only (1 sensor per finger, no meaningful torque)

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Per-Finger Force Comparison                 │
    │  (info label)                                │
    ├──────┬──────┬──────┬──────┬──────────────────┤
    │Thumb │Index │Middle│ Ring │ Pinky            │
    │[comp]│[comp]│[comp]│[comp]│ [compass]        │
    ├──────┴──────┴──────┴──────┴──────────────────┤
    │  [Force6DChart - Global sum of all fingers]  │
    └──────────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.is_revo2 = False
        self.sensor_counts = REVO1_SENSOR_COUNTS
        self.total_sensors = REVO1_TOTAL_SENSORS
        self._setup_ui()

    def set_hardware_type(self, hw_type):
        """Configure widget for Revo1 or Revo2 touch"""
        try:
            from common_imports import uses_revo2_touch_api
            self.is_revo2 = uses_revo2_touch_api(hw_type)
        except Exception:
            self.is_revo2 = False

        if self.is_revo2:
            self.sensor_counts = REVO2_SENSOR_COUNTS
            self.total_sensors = REVO2_TOTAL_SENSORS
            self.info_label.setText(
                "Revo2: 5 output groups (1 per finger) · 3D force per finger"
            )
        else:
            self.sensor_counts = REVO1_SENSOR_COUNTS
            self.total_sensors = REVO1_TOTAL_SENSORS
            self.info_label.setText(
                f"Revo1: {self.total_sensors} sensors (2~3 per finger) · 6D force/torque per finger"
            )

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("Per-Finger Force Comparison")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Info label
        self.info_label = QLabel(
            f"Revo1: {self.total_sensors} sensors (2~3 per finger) · 6D force/torque per finger"
        )
        self.info_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; font-style: italic;"
        )
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        # --- 5 Finger ForceTorqueFingerCharts side-by-side ---
        charts_layout = QHBoxLayout()
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(2)

        self.finger_charts = []
        for i, (name, color) in enumerate(zip(TOUCH_NAMES_EN, FINGER_COLORS_FORCE)):
            chart = ForceTorqueFingerChart(name, color)
            self.finger_charts.append(chart)
            charts_layout.addWidget(chart, 1)

        layout.addLayout(charts_layout, 2)

        # --- Force6D time-series chart (sum of all fingers) ---
        if HAS_FORCE6D_CHART:
            try:
                self.force6d_chart = Force6DChart(
                    title="Total Force/Torque (all fingers)",
                    components=6,
                    max_points=200,
                    show_values=False,  # Values shown in compass charts above
                    accent_color=(93, 156, 236),
                )
                layout.addWidget(self.force6d_chart, 1)
            except Exception:
                self.force6d_chart = None
        else:
            self.force6d_chart = None

    def update_data(self, per_finger_forces: dict):
        """Update with per-finger force data from GlobalForceCalculator.calculate_per_finger()

        Args:
            per_finger_forces: dict mapping finger_name -> [Fx,Fy,Fz,Mx,My,Mz]
        """
        if not per_finger_forces:
            return

        # Accumulate total force for the sum chart
        total_force6d = np.zeros(6)

        for i, name in enumerate(TOUCH_NAMES_EN):
            finger_key = name.lower()
            if finger_key not in per_finger_forces:
                continue

            force6d = per_finger_forces[finger_key]

            # Update compass chart (6-param: Fx, Fy, Fz, Mx, My, Mz)
            if i < len(self.finger_charts):
                fx = float(force6d[0]) if len(force6d) > 0 else 0.0
                fy = float(force6d[1]) if len(force6d) > 1 else 0.0
                fz = float(force6d[2]) if len(force6d) > 2 else 0.0
                mx = float(force6d[3]) if len(force6d) > 3 else 0.0
                my = float(force6d[4]) if len(force6d) > 4 else 0.0
                mz = float(force6d[5]) if len(force6d) > 5 else 0.0
                self.finger_charts[i].add_data(fx, fy, fz, mx, my, mz)

            # Accumulate total
            total_force6d += np.array(force6d[:6], dtype=float)

        # Update sum chart
        if self.force6d_chart:
            self.force6d_chart.add_data_array(total_force6d)

    def clear(self):
        """Clear all data"""
        for chart in self.finger_charts:
            chart.clear()
        if self.force6d_chart:
            self.force6d_chart.clear()
