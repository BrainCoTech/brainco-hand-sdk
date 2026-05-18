"""Touch Sensor Shared Components

Common chart widgets, constants, and utilities used across all touch sensor panels:
- PressureTouchPanel (Modulus/Pressure)
- ForceTouchPanel (ArrayPressure/Force-Torque)
"""

import asyncio
import numpy as np
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QGridLayout, QTabWidget,
    QFrame, QProgressBar, QComboBox, QScrollArea
)
from PySide6.QtCore import Qt, QTimer

from .styles import COLORS
from common_imports import logger


def run_async(coro):
    """Run async coroutine in a new event loop (for Qt callbacks)"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    pg = None  # type: ignore
    HAS_PYQTGRAPH = False


# =============================================================================
# Shared Chart Widgets
# =============================================================================

class SummaryChart(QWidget):
    """Real-time multi-line chart for summary data (force, pressure, etc.)"""

    def __init__(self, title: str = "Summary", y_range: tuple = (0, 5000),
                 sensor_names: list = None, sensor_colors: list = None,
                 y_label: str = "mN"):
        super().__init__()
        self.title = title
        self.y_range = y_range
        self.sensor_names = sensor_names or []
        self.sensor_colors = sensor_colors or []
        self.sensor_count = len(self.sensor_names)
        self.y_label = y_label
        self.curves = []
        self.data = [[] for _ in range(self.sensor_count)]
        self.max_points = 200
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_PYQTGRAPH and pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.setBackground('#1a1a2e')
            self.plot.showGrid(x=True, y=True, alpha=0.3)
            self.plot.setYRange(self.y_range[0], self.y_range[1])
            self.plot.setXRange(0, self.max_points)
            self.plot.setTitle(self.title, color='w', size='10pt')
            self.plot.setLabel('bottom', 'samples', color='w')
            self.plot.setLabel('left', self.y_label, color='w')

            self.plot.addLegend(offset=(-10, 10))

            for i, (name, color) in enumerate(zip(self.sensor_names, self.sensor_colors)):
                pen = pg.mkPen(color=color, width=2)
                curve = self.plot.plot([], [], pen=pen, name=name)
                self.curves.append(curve)
            layout.addWidget(self.plot)
        else:
            layout.addWidget(QLabel("pyqtgraph not installed"))

    def add_data(self, values: list):
        """Add data for all sensors"""
        for i, val in enumerate(values[:self.sensor_count]):
            self.data[i].append(val)
            if len(self.data[i]) > self.max_points:
                self.data[i].pop(0)
        self._update_curves()

    def _update_curves(self):
        if not HAS_PYQTGRAPH:
            return
        for i, curve in enumerate(self.curves):
            if self.data[i]:
                curve.setData(list(range(len(self.data[i]))), self.data[i])

    def clear(self):
        self.data = [[] for _ in range(self.sensor_count)]
        self._update_curves()

    def set_sensor_visible(self, sensor_idx: int, visible: bool):
        """Show/hide a sensor curve"""
        if HAS_PYQTGRAPH and sensor_idx < len(self.curves):
            self.curves[sensor_idx].setVisible(visible)


class HeatmapChart(QWidget):
    """2D heatmap chart for pressure/tactile array data with pyqtgraph ImageItem"""

    def __init__(self, module_name: str, point_count: int, color: tuple,
                 rows: int, cols: int, coord_map: list = None):
        super().__init__()
        self.module_name = module_name
        self.point_count = point_count
        self.color = color
        self.rows = rows
        self.cols = cols
        self.coord_map = coord_map  # list of (row, col) tuples, or None for divmod fallback
        self.current_values = [0] * point_count
        self._setup_ui()

    def _get_coords(self, i: int):
        """Get (row, col) for point index i, using coord_map if available"""
        if self.coord_map and i < len(self.coord_map):
            return self.coord_map[i]
        return divmod(i, self.cols)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # -- Header: module name + stats --
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1a1a2e; border-radius: 6px; padding: 4px 8px;")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(8, 4, 8, 4)
        r, g, b = self.color
        name_label = QLabel(f"🔥 {self.module_name} ({self.point_count} pts)")
        name_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffeb3b;"
        )
        header.addWidget(name_label)
        header.addStretch()
        self.stats_label = QLabel("max: 0  sum: 0  avg: 0")
        self.stats_label.setStyleSheet(
            "font-size: 14px; font-family: 'Courier New'; color: #eee;"
        )
        header.addWidget(self.stats_label)
        layout.addWidget(header_frame)

        # -- Body: heatmap --
        if HAS_PYQTGRAPH and pg is not None:
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('#1a1a2e')
            self.plot_widget.hideAxis('bottom')
            self.plot_widget.hideAxis('left')
            self.plot_widget.getViewBox().invertY(True)

            # Colormap: black -> blue -> cyan -> yellow -> red
            positions = [0.0, 0.25, 0.5, 0.75, 1.0]
            colors_rgb = [
                (0, 0, 0),
                (0, 0, 180),
                (0, 200, 200),
                (220, 220, 0),
                (255, 50, 0),
            ]
            self.cmap = pg.ColorMap(positions, colors_rgb)
            self.lut = self.cmap.getLookupTable(nPts=256)

            self.img_item = pg.ImageItem()
            self.img_item.setLookupTable(self.lut)
            self.plot_widget.addItem(self.img_item)

            # Initialize 2D grid with zeros instead of nan (nan breaks pyqtgraph ImageItem)
            self._data_2d = np.zeros((self.rows, self.cols), dtype=np.float64)
            valid_coords = set()
            for i in range(self.point_count):
                r_idx, c_idx = self._get_coords(i)
                if r_idx < self.rows and c_idx < self.cols:
                    valid_coords.add((r_idx, c_idx))
                    
            # Explicitly draw empty placeholders for missing sensors
            for r in range(self.rows):
                for c in range(self.cols):
                    if (r, c) not in valid_coords:
                        # Draw a distinct dark dotted/dashed box to indicate 'No Sensor Layout Hole'
                        rect = pg.QtWidgets.QGraphicsRectItem(c, r, 1, 1)
                        rect.setPen(pg.mkPen('#3a3a5a', width=1, style=Qt.DashLine))
                        rect.setBrush(pg.mkBrush(20, 20, 30, 200))
                        self.plot_widget.addItem(rect)

            self.img_item.setImage(self._data_2d.T, levels=(0, 500))

            # Text overlays
            self.text_items = []
            for i in range(self.point_count):
                r_idx, c_idx = self._get_coords(i)
                if r_idx < self.rows and c_idx < self.cols:
                    txt = pg.TextItem(str(i + 1), color='w', anchor=(0.5, 0.5))
                    txt.setFont(pg.QtGui.QFont('Courier New', 11))
                    txt.setPos(c_idx + 0.5, r_idx + 0.5)
                    self.plot_widget.addItem(txt)
                    self.text_items.append(txt)

            # Colorbar
            try:
                bar_item = pg.ColorBarItem(
                    values=(0, 500), colorMap=self.cmap,
                    interactive=False, width=15,
                )
                bar_item.setImageItem(self.img_item, insert_in=self.plot_widget.plotItem)
            except Exception:
                pass

            layout.addWidget(self.plot_widget, 1)
        else:
            layout.addWidget(QLabel("pyqtgraph required"), 1)

    def add_data(self, values: list):
        """Update heatmap with new values"""
        n = min(len(values), self.point_count)
        self.current_values = list(values[:n]) + [0] * max(0, self.point_count - n)

        for i in range(self.point_count):
            r_idx, c_idx = self._get_coords(i)
            if r_idx < self.rows and c_idx < self.cols:
                self._data_2d[r_idx, c_idx] = float(self.current_values[i])

        valid = [v for v in self.current_values if v > 0]
        max_val = max(valid) if valid else 100
        level_max = max(100, max_val * 1.2)

        if HAS_PYQTGRAPH:
            self.img_item.setImage(self._data_2d.T, levels=(0, level_max))

            for i, txt in enumerate(self.text_items):
                val = self.current_values[i]
                txt.setText(str(val))
                if val > level_max * 0.5:
                    txt.setColor('k')
                else:
                    txt.setColor('w')

        total = sum(self.current_values)
        avg = total / self.point_count if self.point_count else 0
        self.stats_label.setText(
            f"max: {max(self.current_values)}  sum: {total}  avg: {avg:.0f}"
        )

    def clear(self):
        self.current_values = [0] * self.point_count
        for i in range(self.point_count):
            r_idx, c_idx = self._get_coords(i)
            if r_idx < self.rows and c_idx < self.cols:
                self._data_2d[r_idx, c_idx] = 0.0
        if HAS_PYQTGRAPH:
            self.img_item.setImage(self._data_2d.T, levels=(0, 500))
            for txt in self.text_items:
                txt.setText("0")
                txt.setColor('w')
        self.stats_label.setText("max: 0  sum: 0  avg: 0")


def build_status_cards(parent_layout, sensor_names, sensor_colors, is_compact=False):
    """Build sensor status cards with progress bars and value labels.

    Returns: (sensor_cards, sensor_bars, sensor_labels)
    """
    title = QLabel("📊 Sensor Status")
    title.setStyleSheet("font-weight: bold; font-size: 12px;")
    parent_layout.addWidget(title)

    sensor_cards = []
    sensor_bars = []
    sensor_labels = []

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

    cards_widget = QWidget()
    cards_layout = QVBoxLayout(cards_widget)
    cards_layout.setContentsMargins(0, 0, 0, 0)
    cards_layout.setSpacing(2 if is_compact else 4)

    for i, (name, color) in enumerate(zip(sensor_names, sensor_colors)):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border-left: 4px solid rgb{color};
                border-radius: 4px;
                padding: 2px;
            }}
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(6, 2, 6, 2)
        card_layout.setSpacing(6)

        name_label = QLabel(name)
        name_label.setFixedWidth(80 if is_compact else 50)
        name_label.setStyleSheet(f"color: rgb{color}; font-weight: bold; font-size: 13px;")
        card_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setRange(0, 5000)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(14 if is_compact else 16)
        r, g, b = color
        bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #2a2a3e;
            }}
            QProgressBar::chunk {{
                background-color: rgb({r}, {g}, {b});
                border-radius: 2px;
            }}
        """)
        card_layout.addWidget(bar, 1)
        sensor_bars.append(bar)

        val_label = QLabel("0")
        val_label.setFixedWidth(50)
        val_label.setAlignment(Qt.AlignRight)
        val_label.setStyleSheet(
            "font-family: 'Courier New'; font-size: 13px;"
        )
        card_layout.addWidget(val_label)
        sensor_labels.append(val_label)

        cards_layout.addWidget(card)
        sensor_cards.append(card)

    scroll.setWidget(cards_widget)
    parent_layout.addWidget(scroll, 1)

    return sensor_cards, sensor_bars, sensor_labels
