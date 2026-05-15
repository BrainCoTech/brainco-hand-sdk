"""Reusable Force6D Chart Widget

A pyqtgraph-based time-series chart for displaying 6D force/torque data.
Can be configured for:
- Full 6D (Fx, Fy, Fz, Mx, My, Mz) — e.g., Global force, Per-finger force
- 3D force only (Fx, Fy, Fz) — e.g., Revo2 single-sensor fingers
- 5-component (Fx, Fy, Fz, Mx, My) — e.g., ArrayPressure devices

Used by:
- touch_global_force_widget.py (GlobalForceWidget)
- touch_per_finger_force_widget.py (PerFingerForceWidget)
- touch_panel_force.py (ForceTouchSubPanel) - optional migration
"""

from collections import deque
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
)
from PySide6.QtCore import Qt

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    pg = None
    HAS_PYQTGRAPH = False


# Standard color scheme for force/torque components
FORCE6D_COLORS = {
    'Fx': (230, 76, 60),     # Red
    'Fy': (39, 174, 96),     # Green
    'Fz': (52, 152, 219),    # Blue
    'Mx': (230, 126, 34),    # Orange
    'My': (155, 89, 182),    # Purple
    'Mz': (26, 188, 156),    # Teal
}

FORCE6D_LABELS = ['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz']


class Force6DChart(QWidget):
    """Reusable time-series chart for force/torque visualization.

    Supports configurable number of components (3D, 5D, or full 6D).
    Features:
    - Real-time time-series plot with auto-scrolling
    - Numeric value display panel (optional)
    - Configurable title, color, and axis range
    """

    def __init__(
        self,
        title: str = "Force/Torque",
        components: int = 6,
        max_points: int = 200,
        show_values: bool = True,
        accent_color: tuple = None,
        force_range: tuple = None,
        torque_range: tuple = None,
    ):
        """
        Args:
            title: Chart title
            components: Number of force/torque components (3=Fx/Fy/Fz, 5=+Mx/My, 6=+Mz)
            max_points: Max time-series history length
            show_values: Whether to show numeric value labels
            accent_color: Optional (r,g,b) accent for title highlight
            force_range: Optional (min, max) Y-axis range for force (N)
            torque_range: Optional (min, max) Y-axis range for torque (N·m)
        """
        super().__init__()
        self.components = min(components, 6)
        self.max_points = max_points
        self.show_values = show_values
        self.title_text = title
        self.accent_color = accent_color

        # Labels for active components
        self.labels = FORCE6D_LABELS[:self.components]
        self.colors = [FORCE6D_COLORS[l] for l in self.labels]

        # Data buffers
        self.data = {label: deque(maxlen=max_points) for label in self.labels}

        # Axis ranges
        self.force_range = force_range  # None = auto-range
        self.torque_range = torque_range

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        if not HAS_PYQTGRAPH or pg is None:
            layout.addWidget(QLabel("pyqtgraph required for chart display"))
            self.plot_widget = None
            return

        # --- Chart ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1a1a2e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setXRange(0, self.max_points)

        # Title
        if self.accent_color:
            r, g, b = self.accent_color
            self.plot_widget.setTitle(self.title_text, color=(r, g, b), size='10pt')
        else:
            self.plot_widget.setTitle(self.title_text, color='#aaa', size='10pt')

        self.plot_widget.setLabel('bottom', 'samples', color='#888')

        # Y-axis auto-range or fixed
        if self.force_range and self.components <= 3:
            self.plot_widget.setYRange(*self.force_range)
            self.plot_widget.setLabel('left', 'N', color='#888')
        else:
            self.plot_widget.enableAutoRange(axis='y', enable=True)
            self.plot_widget.setLabel('left', 'N / N·m', color='#888')

        # Add legend (must be before plot() calls for pyqtgraph to register names)
        self.plot_widget.addLegend(offset=(-10, 10))

        # Create curves
        self.curves = {}
        for label in self.labels:
            r, g, b = FORCE6D_COLORS[label]
            pen = pg.mkPen(color=(r, g, b), width=2)
            curve = self.plot_widget.plot([], [], pen=pen, name=label)
            self.curves[label] = curve

        layout.addWidget(self.plot_widget, 1)

        # --- Value display panel (optional) ---
        if self.show_values:
            values_frame = QFrame()
            values_frame.setStyleSheet(
                "background-color: #1a1a2e; border-radius: 4px; padding: 2px;"
            )
            values_layout = QGridLayout(values_frame)
            values_layout.setContentsMargins(4, 2, 4, 2)
            values_layout.setSpacing(2)

            self.value_labels = {}
            for i, label in enumerate(self.labels):
                r, g, b = FORCE6D_COLORS[label]

                name_lbl = QLabel(f"{label}:")
                name_lbl.setStyleSheet(
                    f"font-size: 11px; font-weight: bold; color: rgb({r},{g},{b});"
                )

                val_lbl = QLabel("0.00")
                val_lbl.setStyleSheet(
                    "font-size: 12px; font-family: 'Courier New'; "
                    "color: #eee;"
                )
                val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                val_lbl.setMinimumWidth(70)

                unit_lbl = QLabel("N" if i < 3 else "N·m")
                unit_lbl.setStyleSheet("font-size: 10px; color: #888;")

                # Layout: 3 per row for 6D, or all in one row for 3D
                if self.components <= 3:
                    row, col = 0, i * 3
                else:
                    row, col = divmod(i, 3)
                    col *= 3

                values_layout.addWidget(name_lbl, row, col)
                values_layout.addWidget(val_lbl, row, col + 1)
                values_layout.addWidget(unit_lbl, row, col + 2)
                self.value_labels[label] = val_lbl

            layout.addWidget(values_frame)
        else:
            self.value_labels = {}

    def add_data(self, *values):
        """Add a data point.

        Args:
            values: Force/torque values in order (Fx, Fy, Fz, [Mx, My, [Mz]])
                    Number of values should match self.components
        """
        for i, label in enumerate(self.labels):
            val = values[i] if i < len(values) else 0.0
            self.data[label].append(float(val))

        # Update curves
        if self.plot_widget:
            for label in self.labels:
                buf = self.data[label]
                x = list(range(len(buf)))
                self.curves[label].setData(x, list(buf))

        # Update value labels
        if self.value_labels:
            for i, label in enumerate(self.labels):
                val = values[i] if i < len(values) else 0.0
                if i < 3:
                    self.value_labels[label].setText(f"{val:+.2f}")
                else:
                    self.value_labels[label].setText(f"{val:+.4f}")

    def add_data_array(self, force6d):
        """Add data from a numpy array or list [Fx, Fy, Fz, Mx, My, Mz]"""
        self.add_data(*force6d[:self.components])

    def clear(self):
        """Clear all data"""
        for label in self.labels:
            self.data[label].clear()

        if self.plot_widget:
            for label in self.labels:
                self.curves[label].setData([], [])

        if self.value_labels:
            for label in self.value_labels:
                self.value_labels[label].setText("0.00")
