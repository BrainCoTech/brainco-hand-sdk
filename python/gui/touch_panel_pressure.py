"""Pressure Touch Panel - For Revo2 Pressure Touch devices

Displays distributed scalar pressure data:
- 5 fingers × 9 sampling points (staggered 3×3 layout)
- 1 palm × 46 sampling points (irregular fan layout)

Tabs:
- Summary: 6-sensor force curves + status cards
- Detail: Heatmap per sensor (5 fingers + palm)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QTabWidget
)

from .touch_common import (
    SummaryChart, HeatmapChart, build_status_cards,
    run_async, logger
)
from .i18n import tr


# Sensor configuration
SENSOR_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky", "Palm"]
SENSOR_COLORS = [
    (255, 100, 100),   # Thumb - Red
    (100, 255, 100),   # Index - Green
    (100, 100, 255),   # Middle - Blue
    (255, 255, 100),   # Ring - Yellow
    (255, 100, 255),   # Pinky - Magenta
    (100, 255, 255),   # Palm - Cyan
]

SENSOR_POINTS = {
    "Thumb": 9, "Index": 9, "Middle": 9, "Ring": 9, "Pinky": 9, "Palm": 46,
}

# Heatmap layout: (rows, cols)
# Fingers: 6×3 grid (vertical staggered honeycomb, tip points up)
# Palm: 11×9 irregular fan shape
HEATMAP_LAYOUT = {
    "Thumb": (6, 3), "Index": (6, 3), "Middle": (6, 3),
    "Ring": (6, 3), "Pinky": (6, 3),
    "Palm": (11, 9),
}

# Finger 9-point staggered coord_map (vertical honeycomb pattern)
# Physical layout rotated 90 deg (tip points UP, base points DOWN):
# Grid 6×3:
#      c0  c1  c2
# r0:   _   8   _   (Tip)
# r1:   7   _   9
# r2:   _   5   _
# r3:   4   _   6
# r4:   _   2   _
# r5:   1   _   3   (Base)
FINGER_COORD_MAP = [
    # pt1     pt2     pt3     (base)
    (5, 0), (4, 1), (5, 2),
    # pt4     pt5     pt6     (middle)
    (3, 0), (2, 1), (3, 2),
    # pt7     pt8     pt9     (tip)
    (1, 0), (0, 1), (1, 2),
]

# Palm 46-point coord_map (irregular fan shape, from layout diagram)
# Organized horizontally row by row based on physical layout
#   c0 c1 c2 c3 c4 c5 c6 c7 c8
# 0:[1][2][3][4][5][6][7][16][8]
# 1:[9][10][11][12][13][14][15][23]
# 2:[17][18][19][20][21][22]
# 3:[24][25][26][27][28]
# 4:[29][30][31][32]
# 5:[33][34][35]
# 6:[36][37][38]
# 7:[39][40]
# 8:[41][42]
# 9:[43][44]
# 10:[45][46]
PALM_COORD_MAP = [
    # index = sensor_number - 1, value = (row, col)
    (0,0), (0,1), (0,2), (0,3), (0,4), (0,5), (0,6),         # 1-7
    (0,8),                                                   # 8
    (1,0), (1,1), (1,2), (1,3), (1,4), (1,5), (1,6),         # 9-15
    (0,7),                                                   # 16
    (2,0), (2,1), (2,2), (2,3), (2,4), (2,5),                # 17-22
    (1,7),                                                   # 23
    (3,0), (3,1), (3,2), (3,3), (3,4),                       # 24-28
    (4,0), (4,1), (4,2), (4,3),                              # 29-32
    (5,0), (5,1), (5,2),                                     # 33-35
    (6,0), (6,1), (6,2),                                     # 36-38
    (7,0), (7,1),                                            # 39-40
    (8,0), (8,1),                                            # 41-42
    (9,0), (9,1),                                            # 43-44
    (10,0),(10,1),                                           # 45-46
]


def _get_coord_map(sensor_name: str):
    """Get coordinate map for a sensor"""
    if sensor_name == "Palm":
        return PALM_COORD_MAP
    if sensor_name in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        return FINGER_COORD_MAP
    return None


class PressureTouchSubPanel(QWidget):
    """Pressure Touch Panel for Pressure Touch devices.

    Tabs:
    - Summary: 6-sensor force curves + status cards
    - Detail: Heatmap per sensor (5 fingers + palm)
    """

    def __init__(self):
        super().__init__()
        self.detail_charts = []
        self.sensor_cards = []
        self.sensor_bars = []
        self.sensor_labels = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tabs = QTabWidget()

        # --- Tab 1: Summary ---
        overview_widget = QWidget()
        overview_layout = QGridLayout(overview_widget)
        overview_layout.setSpacing(8)

        self.summary_chart = SummaryChart(
            "Pressure Summary (mN)", (0, 5000),
            sensor_names=SENSOR_NAMES,
            sensor_colors=SENSOR_COLORS,
            y_label="mN"
        )
        overview_layout.addWidget(self.summary_chart, 0, 0, 2, 1)

        # Status cards
        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setSpacing(4)
        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            status_layout, SENSOR_NAMES, SENSOR_COLORS
        )
        overview_layout.addWidget(status_widget, 0, 1, 2, 1)
        overview_layout.setColumnStretch(0, 3)
        overview_layout.setColumnStretch(1, 1)

        self.tabs.addTab(overview_widget, "📊 Summary")

        # --- Detail tabs: one heatmap per sensor ---
        self.detail_charts = []
        for i, (name, color) in enumerate(zip(SENSOR_NAMES, SENSOR_COLORS)):
            point_count = SENSOR_POINTS[name]
            rows, cols = HEATMAP_LAYOUT[name]
            coord_map = _get_coord_map(name)
            chart = HeatmapChart(name, point_count, color, rows, cols, coord_map=coord_map)
            self.detail_charts.append(chart)
            icon = "🖐" if name == "Palm" else "👆"
            self.tabs.addTab(chart, f"{icon} {name}")

        layout.addWidget(self.tabs, 1)

    def update_summary(self, summary_data: list):
        """Update summary chart and status cards.

        summary_data: list of 6 values (one per sensor, mN)
        """
        if not summary_data:
            return
        valid = [v if v is not None else 0 for v in summary_data[:6]]

        self.summary_chart.add_data(valid)

        for i, val in enumerate(valid):
            if i < len(self.sensor_bars):
                self.sensor_bars[i].setValue(min(val, 5000))
                self.sensor_labels[i].setText(f"{val} mN")

    def update_detail(self, detailed_data: list):
        """Update detail heatmaps.

        detailed_data: list of 6 PressureDetailedItem (one per sensor)
        """
        if not detailed_data:
            return
        for i, item in enumerate(detailed_data[:6]):
            if item is None:
                continue
            sensor_values = item.sensors if hasattr(item, 'sensors') else []
            if i < len(self.detail_charts) and sensor_values:
                self.detail_charts[i].add_data(sensor_values)

    def clear(self):
        self.summary_chart.clear()
        for chart in self.detail_charts:
            chart.clear()
