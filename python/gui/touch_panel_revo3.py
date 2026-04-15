"""V3 Touch Panel - For Revo3 Tactile Array devices

Displays V3 tactile array data:
- Summary: 16 values (palm + 5 fingers × 3 locations)
- Detail: 11 tactile array modules as heatmaps

Tabs:
- Summary: 16-line curves + status cards
- Per-finger heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QTabWidget
)

from .touch_common import (
    SummaryChart, HeatmapChart, build_status_cards,
    run_async, logger
)


# Summary: 16 values
REVO3_SUMMARY_NAMES = [
    "Palm",
    "Thumb Tip", "Thumb UPad", "Thumb LPad",
    "Index Tip", "Index UPad", "Index LPad",
    "Middle Tip", "Middle UPad", "Middle LPad",
    "Ring Tip", "Ring UPad", "Ring LPad",
    "Pinky Tip", "Pinky UPad", "Pinky LPad",
]

REVO3_SUMMARY_COLORS = [
    (100, 255, 255),
    (255, 100, 100), (255, 140, 140), (200, 60, 60),
    (100, 255, 100), (140, 255, 140), (60, 200, 60),
    (100, 100, 255), (140, 140, 255), (60, 60, 200),
    (255, 255, 100), (255, 255, 140), (200, 200, 60),
    (255, 100, 255), (255, 140, 255), (200, 60, 200),
]

# Detail: 11 modules
REVO3_MODULE_NAMES = [
    "Palm", "ThumbTip", "ThumbPad", "IndexTip", "IndexPad",
    "MiddleTip", "MiddlePad", "RingTip", "RingPad", "PinkyTip", "PinkyPad"
]

REVO3_MODULE_COLORS = [
    (0, 230, 230),
    (255, 100, 100), (255, 160, 120),
    (100, 255, 100), (140, 255, 160),
    (100, 140, 255), (140, 180, 255),
    (255, 255, 100), (255, 220, 140),
    (255, 100, 255), (255, 160, 230),
]

REVO3_MODULE_POINTS = {
    "Palm": 29,
    "ThumbTip": 22, "ThumbPad": 44,
    "IndexTip": 21, "IndexPad": 29,
    "MiddleTip": 21, "MiddlePad": 29,
    "RingTip": 21, "RingPad": 29,
    "PinkyTip": 21, "PinkyPad": 29,
}

REVO3_HEATMAP_LAYOUT = {
    "Palm":      (8, 7),
    "ThumbTip":  (7, 6),
    "ThumbPad":  (12, 6),
    "IndexTip":  (8, 5), "IndexPad":  (9, 6),
    "MiddleTip": (8, 5), "MiddlePad": (9, 6),
    "RingTip":   (8, 5), "RingPad":   (9, 6),
    "PinkyTip":  (8, 5), "PinkyPad":  (9, 6),
}

# Explicit coordinate maps (from physical layout diagrams)
# Format: coord_map[i] = (row, col) in heatmap grid  (sensor index = i+1)
# Reference images: docs/touch/images/revo3_*.png (right-side black grid)
REVO3_COORD_MAP = {
    # ThumbTip — 22 pts, grid 7 rows × 6 cols (image x:0-5, y:0-6)
    # col:  0    1    2    3    4    5
    # row0: [1]  [2]  [3]  [4]  [ ]  [ ]
    # row1: [5]  [6]  [7]  [8]  [17] [ ]
    # row2: [9]  [10] [11] [12] [18] [ ]
    # row3: [13] [14] [15] [16] [19] [ ]
    # row4: [ ]  [ ]  [ ]  [ ]  [ ]  [20]
    # row5: [ ]  [ ]  [ ]  [ ]  [ ]  [21]
    # row6: [ ]  [ ]  [ ]  [ ]  [ ]  [22]
    "ThumbTip": [
        (0, 0), (0, 1), (0, 2), (0, 3),           # 1-4
        (1, 0), (1, 1), (1, 2), (1, 3),           # 5-8
        (2, 0), (2, 1), (2, 2), (2, 3),           # 9-12
        (3, 0), (3, 1), (3, 2), (3, 3),           # 13-16
        (1, 4), (2, 4), (3, 4),                   # 17-19
        (4, 5), (5, 5), (6, 5),                   # 20-22
    ],

    # ThumbPad — 44 pts, grid 12 rows × 6 cols (image x:0-5, y:0-12)
    # Main body 40pts: 5 cols × 8 rows, col-major from bottom to top (row7→0)
    # col:  0    1    2    3    4    5
    # row0: [8]  [16] [24] [32] [40] [ ]
    # row1: [7]  [15] [23] [31] [39] [ ]
    # row2: [6]  [14] [22] [30] [38] [ ]
    # row3: [5]  [13] [21] [29] [37] [ ]
    # row4: [4]  [12] [20] [28] [36] [ ]
    # row5: [3]  [11] [19] [27] [35] [ ]
    # row6: [2]  [10] [18] [26] [34] [ ]
    # row7: [1]  [9]  [17] [25] [33] [ ]
    # row8: [ ]  [ ]  [ ]  [ ]  [ ]  [41]
    # row9: [ ]  [ ]  [ ]  [ ]  [ ]  [42]
    # row10:[ ]  [ ]  [ ]  [ ]  [ ]  [43]
    # row11:[ ]  [ ]  [ ]  [ ]  [ ]  [44]
    "ThumbPad": [
        (7, 0), (6, 0), (5, 0), (4, 0), (3, 0), (2, 0), (1, 0), (0, 0),   # 1-8   col0
        (7, 1), (6, 1), (5, 1), (4, 1), (3, 1), (2, 1), (1, 1), (0, 1),   # 9-16  col1
        (7, 2), (6, 2), (5, 2), (4, 2), (3, 2), (2, 2), (1, 2), (0, 2),   # 17-24 col2
        (7, 3), (6, 3), (5, 3), (4, 3), (3, 3), (2, 3), (1, 3), (0, 3),   # 25-32 col3
        (7, 4), (6, 4), (5, 4), (4, 4), (3, 4), (2, 4), (1, 4), (0, 4),   # 33-40 col4
        (8, 5), (9, 5), (10, 5), (11, 5),                                 # 41-44 col5
    ],

    # FourFingerTip (Index/Middle/Ring/Pinky Tip) — 21 pts, 8 rows × 5 cols
    # (image x:0-4, y:0-8)
    # col:  0    1    2    3    4
    # row0: [1]  [2]  [3]  [ ]  [ ]
    # row1: [4]  [5]  [6]  [ ]  [ ]
    # row2: [7]  [8]  [9]  [16] [ ]
    # row3: [10] [11] [12] [17] [ ]
    # row4: [13] [14] [15] [18] [ ]
    # row5: [ ]  [ ]  [ ]  [ ]  [19]
    # row6: [ ]  [ ]  [ ]  [ ]  [20]
    # row7: [ ]  [ ]  [ ]  [ ]  [21]
    "FourFingerTip": [
        (0, 0), (0, 1), (0, 2),           # 1-3
        (1, 0), (1, 1), (1, 2),           # 4-6
        (2, 0), (2, 1), (2, 2),           # 7-9
        (3, 0), (3, 1), (3, 2),           # 10-12
        (4, 0), (4, 1), (4, 2),           # 13-15
        (2, 3), (3, 3), (4, 3),           # 16-18
        (5, 4), (6, 4), (7, 4),           # 19-21
    ],

    # FourFingerPad (Index/Middle/Ring/Pinky Pad) — 29 pts, 9 rows × 6 cols
    # (image x:0-5, y:0-9)
    # col:  0    1    2    3    4    5
    # row0: [1]  [2]  [3]  [4]  [5]  [ ]
    # row1: [6]  [7]  [8]  [9]  [10] [ ]
    # row2: [11] [12] [13] [14] [15] [ ]
    # row3: [16] [17] [18] [19] [20] [ ]
    # row4: [21] [22] [23] [24] [25] [ ]
    # row5: [ ]  [ ]  [ ]  [ ]  [ ]  [26]
    # row6: [ ]  [ ]  [ ]  [ ]  [ ]  [27]
    # row7: [ ]  [ ]  [ ]  [ ]  [ ]  [28]
    # row8: [ ]  [ ]  [ ]  [ ]  [ ]  [29]
    "FourFingerPad": [
        (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),   # 1-5
        (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),   # 6-10
        (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),   # 11-15
        (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),   # 16-20
        (4, 0), (4, 1), (4, 2), (4, 3), (4, 4),   # 21-25
        (5, 5), (6, 5), (7, 5), (8, 5),           # 26-29
    ],

    # Palm (Left Hand) — 29 pts, 8 rows × 7 cols (image x:0-6, y:0-8)
    # col:  0    1    2    3    4    5    6
    # row0: [28] [26] [23] [20] [16] [9]  [1]
    # row1: [29] [27] [24] [21] [17] [10] [2]
    # row2: [ ]  [ ]  [25] [22] [18] [11] [3]
    # row3: [ ]  [ ]  [ ]  [ ]  [19] [12] [4]
    # row4: [ ]  [ ]  [ ]  [ ]  [ ]  [13] [5]
    # row5: [ ]  [ ]  [ ]  [ ]  [ ]  [14] [6]
    # row6: [ ]  [ ]  [ ]  [ ]  [ ]  [15] [7]
    # row7: [ ]  [ ]  [ ]  [ ]  [ ]  [ ]  [8]
    "Palm": [
        # index = sensor_number - 1, value = (row, col)
        (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),  # 1-8   col6 (rightmost)
        (0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (5, 5), (6, 5),          # 9-15  col5
        (0, 4), (1, 4), (2, 4), (3, 4),                                  # 16-19 col4
        (0, 3), (1, 3), (2, 3),                                          # 20-22 col3
        (0, 2), (1, 2), (2, 2),                                          # 23-25 col2
        (0, 1), (1, 1),                                                  # 26-27 col1
        (0, 0), (1, 0),                                                  # 28-29 col0
    ],
}


def _get_v3_coord_map(module_name: str):
    """Get coordinate map for a V3 touch module"""
    if module_name in REVO3_COORD_MAP:
        return REVO3_COORD_MAP[module_name]
    if module_name in ("IndexTip", "MiddleTip", "RingTip", "PinkyTip"):
        return REVO3_COORD_MAP["FourFingerTip"]
    if module_name in ("IndexPad", "MiddlePad", "RingPad", "PinkyPad"):
        return REVO3_COORD_MAP["FourFingerPad"]
    return None


class V3TouchSubPanel(QWidget):
    """V3 Touch Panel for Revo3 Tactile Array devices.

    Tabs:
    - Summary: 16-line curves + status cards
    - Per-finger: Heatmap tabs (Palm, Thumb, Index, Middle, Ring, Pinky)
    """

    def __init__(self):
        super().__init__()
        self.detail_charts = [None] * 11
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
            "Touch Summary", (0, 5000),
            sensor_names=REVO3_SUMMARY_NAMES,
            sensor_colors=REVO3_SUMMARY_COLORS,
        )
        overview_layout.addWidget(self.summary_chart, 0, 0, 2, 1)

        status_widget = QWidget()
        status_layout = QVBoxLayout(status_widget)
        status_layout.setSpacing(4)
        self.sensor_cards, self.sensor_bars, self.sensor_labels = build_status_cards(
            status_layout, REVO3_SUMMARY_NAMES, REVO3_SUMMARY_COLORS, is_compact=True
        )
        overview_layout.addWidget(status_widget, 0, 1, 2, 1)
        overview_layout.setColumnStretch(0, 3)
        overview_layout.setColumnStretch(1, 1)

        self.tabs.addTab(overview_widget, "📊 Summary")

        # --- Detail tabs: grouped by finger ---
        v3_finger_groups = [
            ("Palm", "🖐", [(0, "Palm", "Palm")]),
            ("Thumb", "👆", [(1, "Thumb Tip", "ThumbTip"), (2, "Thumb Pad", "ThumbPad")]),
            ("Index", "👆", [(3, "Index Tip", "IndexTip"), (4, "Index Pad", "IndexPad")]),
            ("Middle", "👆", [(5, "Middle Tip", "MiddleTip"), (6, "Middle Pad", "MiddlePad")]),
            ("Ring", "👆", [(7, "Ring Tip", "RingTip"), (8, "Ring Pad", "RingPad")]),
            ("Pinky", "👆", [(9, "Pinky Tip", "PinkyTip"), (10, "Pinky Pad", "PinkyPad")]),
        ]

        for group_name, icon, modules in v3_finger_groups:
            if len(modules) == 1:
                mod_idx, name, mod_key = modules[0]
                color = REVO3_MODULE_COLORS[mod_idx]
                pts = REVO3_MODULE_POINTS[mod_key]
                rows, cols = REVO3_HEATMAP_LAYOUT[mod_key]
                coord_map = _get_v3_coord_map(mod_key)
                chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                self.detail_charts[mod_idx] = chart
                self.tabs.addTab(chart, f"{icon} {group_name}")
            else:
                finger_widget = QWidget()
                finger_layout = QVBoxLayout(finger_widget)
                finger_layout.setContentsMargins(0, 0, 0, 0)
                finger_layout.setSpacing(4)

                for mod_idx, name, mod_key in modules:
                    color = REVO3_MODULE_COLORS[mod_idx]
                    pts = REVO3_MODULE_POINTS[mod_key]
                    rows, cols = REVO3_HEATMAP_LAYOUT[mod_key]
                    coord_map = _get_v3_coord_map(mod_key)
                    chart = HeatmapChart(name, pts, color, rows, cols, coord_map=coord_map)
                    self.detail_charts[mod_idx] = chart
                    finger_layout.addWidget(chart, 1)

                self.tabs.addTab(finger_widget, f"{icon} {group_name}")

        layout.addWidget(self.tabs, 1)

    def update_data(self, v3_data):
        """Process V3 Touch data.

        v3_data: object with .summary (list of 16) and .modules (list of 11 lists)
        """
        if not hasattr(v3_data, 'summary') or not hasattr(v3_data, 'modules'):
            return

        summary = v3_data.summary
        modules = v3_data.modules

        # Update summary
        if summary and len(summary) >= 16:
            summary_16 = list(summary[:16])
            self.summary_chart.add_data(summary_16)
            for i, val in enumerate(summary_16):
                if i < len(self.sensor_bars):
                    self.sensor_bars[i].setValue(min(val, 5000))
                    self.sensor_labels[i].setText(f"{val}")

        # Update detail
        if modules:
            for i, module_points in enumerate(modules):
                if i < len(self.detail_charts) and self.detail_charts[i] is not None and module_points:
                    self.detail_charts[i].add_data(module_points)

    def clear(self):
        self.summary_chart.clear()
        for chart in self.detail_charts:
            if chart is not None:
                chart.clear()
