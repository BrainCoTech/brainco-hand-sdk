"""Mock Vision Touch Panel

Displays mock VisionTouch data for 5 fingertips.
"""

import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QTabWidget, QLabel
)
from PySide6.QtCore import Qt

from .touch_panel_force import ForceTorqueFingerChart
from .touch_common import COLORS

class VisionTouchMockPanel(QWidget):
    """Vision Touch Mock Panel for Revo3 Vision Touch
    
    Tab 1: 6D Force (5 fingertips)
    Tab 2: Camera Input (Placeholder)
    """

    def __init__(self):
        super().__init__()
        self.finger_charts = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tabs = QTabWidget()

        # --- Tab 1: 6D Force for 5 Fingertips ---
        force_widget = QWidget()
        force_layout = QGridLayout(force_widget)
        force_layout.setSpacing(8)

        f_names = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
        f_colors = [
            (255, 100, 100), (100, 255, 100),
            (100, 140, 255), (255, 255, 100), (255, 100, 255)
        ]

        # Layout: 2 rows. Top row: 3 fingers, Bottom row: 2 fingers
        for i in range(5):
            chart = ForceTorqueFingerChart(f"{f_names[i]} Tip", f_colors[i])
            self.finger_charts.append(chart)
            row = i // 3
            col = i % 3
            force_layout.addWidget(chart, row, col)

        self.tabs.addTab(force_widget, "💪 6D Force (5 Tips)")

        # --- Tab 2: Camera Stream Placeholder ---
        cam_widget = QWidget()
        cam_layout = QVBoxLayout(cam_widget)
        cam_lbl = QLabel(
            "📷 Vision Input Stream\n\n"
            "This tab will display the raw or processed camera stream\n"
            "from the 5 fingertip VTai sensors."
        )
        cam_lbl.setAlignment(Qt.AlignCenter)
        cam_lbl.setStyleSheet(f"font-size: 16px; color: {COLORS.get('text_muted', '#888')};")
        cam_layout.addWidget(cam_lbl)
        
        self.tabs.addTab(cam_widget, "📷 Camera Views")

        layout.addWidget(self.tabs)

    def update_data(self, data_list):
        """Update with a list of 5 (fx, fy, fz, mx, my, mz) tuples"""
        if not data_list or len(data_list) < 5:
            return
        for i in range(5):
            fx, fy, fz, mx, my, mz = data_list[i]
            if self.finger_charts[i]:
                self.finger_charts[i].add_data(fx, fy, fz, mx, my, mz)

    def clear(self):
        for chart in self.finger_charts:
            if chart:
                chart.clear()
