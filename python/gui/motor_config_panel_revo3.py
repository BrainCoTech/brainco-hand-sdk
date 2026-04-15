import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGroupBox, QComboBox, QCheckBox, QDoubleSpinBox, QSlider, QSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from .i18n import tr
from .styles import COLORS

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

from .motor_control_panel_revo3 import (
    get_v3_finger_names, get_v3_finger_motors, MOTOR_JOINT_LABELS, get_motor_position_range
)

def run_async(coro_fn):
    async def _wrapper():
        return await coro_fn()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_wrapper())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
    finally:
        loop.close()

# Parameter Type ID
MODE_JOINT_PROTECT = 1
MODE_POS_LIMITS = 2
MODE_SPEED_LIMITS = 3

PARAM_DEF = {
    MODE_POS_LIMITS: (tr("v3_position_limits"), -30.0, 130.0, "°"),
    MODE_SPEED_LIMITS: (tr("v3_speed_limits"), 0.0, 110.0, "rpm"),
    MODE_JOINT_PROTECT: (tr("v3_joint_protect_current"), 0.0, 2000.0, "mA"),
}

class QRangeSlider(QWidget):
    rangeChanged = Signal(float, float)
    sliderReleased = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self._min = 0.0
        self._max = 100.0
        self._low = 0.0
        self._high = 100.0
        self._handle_r = 7
        self._active = None 
        self._drag_offset = 0

    def setRange(self, minimum, maximum):
        self._min = float(minimum)
        self._max = float(maximum)
        if self._low < self._min: self._low = self._min
        if self._high > self._max: self._high = self._max
        self.update()

    def setValues(self, low, high):
        self._low = max(self._min, min(low, self._max))
        self._high = max(self._min, min(high, self._max))
        if self._low > self._high: self._low, self._high = self._high, self._low
        self.update()

    def getValues(self):
        return self._low, self._high

    def _val_to_x(self, val):
        w = self.width() - 2 * self._handle_r
        if self._max == self._min: return self._handle_r
        return self._handle_r + int(w * (val - self._min) / (self._max - self._min))

    def _x_to_val(self, x):
        w = self.width() - 2 * self._handle_r
        if w <= 0: return self._min
        val = self._min + (x - self._handle_r) / w * (self._max - self._min)
        return max(self._min, min(self._max, val))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        h = self.height()
        cy = h // 2
        
        # Track background
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E0E0E0"))
        p.drawRoundedRect(self._handle_r, cy - 2, self.width() - 2*self._handle_r, 4, 2, 2)
        
        # Active track
        x1 = self._val_to_x(self._low)
        x2 = self._val_to_x(self._high)
        p.setBrush(QColor(COLORS.get("primary", "#4CAF50")))
        p.drawRoundedRect(x1, cy - 2, x2 - x1, 4, 2, 2)
        
        # Draw handles
        p.setBrush(QColor("#FFFFFF"))
        pen = QPen(QColor("#999999"))
        pen.setWidth(1)
        p.setPen(pen)
        
        p.drawEllipse(x1 - self._handle_r, cy - self._handle_r, self._handle_r*2, self._handle_r*2)
        p.drawEllipse(x2 - self._handle_r, cy - self._handle_r, self._handle_r*2, self._handle_r*2)

    def mousePressEvent(self, event):
        x = event.position().x()
        x1 = self._val_to_x(self._low)
        x2 = self._val_to_x(self._high)
        
        if abs(x - x1) < self._handle_r * 2 and abs(x - x2) < self._handle_r * 2:
            self._active = 'low' if abs(x - x1) < abs(x - x2) else 'high'
        elif abs(x - x1) < self._handle_r * 2:
            self._active = 'low'
        elif abs(x - x2) < self._handle_r * 2:
            self._active = 'high'
        elif x1 < x < x2:
            self._active = 'bar'
            self._drag_offset = x
        else:
            self._active = None

    def mouseMoveEvent(self, event):
        if not self._active: return
        x = event.position().x()
        if self._active == 'low':
            val = self._x_to_val(x)
            self._low = min(val, self._high)
            self.rangeChanged.emit(self._low, self._high)
        elif self._active == 'high':
            val = self._x_to_val(x)
            self._high = max(val, self._low)
            self.rangeChanged.emit(self._low, self._high)
        elif self._active == 'bar':
            dx = self._x_to_val(x) - self._x_to_val(self._drag_offset)
            span = self._high - self._low
            new_low = max(self._min, min(self._low + dx, self._max - span))
            new_high = new_low + span
            self._low, self._high = new_low, new_high
            self._drag_offset = x
            self.rangeChanged.emit(self._low, self._high)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._active:
            self.sliderReleased.emit()
        self._active = None

class V3ConfigSlider(QWidget):
    """Slider and spinbox for a single motor setting"""
    def __init__(self, motor_id, set_callback):
        super().__init__()
        self.motor_id = motor_id
        self.set_callback = set_callback
        self.current_mode = MODE_POS_LIMITS
        self._slider_scale = 10.0
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        joint = MOTOR_JOINT_LABELS.get(self.motor_id, "")
        label_text = f"M{self.motor_id:02d} {joint}" if joint else f"M{self.motor_id:02d}"
        self.id_label = QLabel(label_text)
        self.id_label.setFixedWidth(65)
        self.id_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self.id_label)

        # Min spinbox
        self.spin_min = QDoubleSpinBox()
        self.spin_min.setFixedWidth(65)
        self.spin_min.setStyleSheet("font-size: 11px;")
        self.spin_min.editingFinished.connect(self._on_spin_changed)
        layout.addWidget(self.spin_min)

        # Range slider
        self.range_slider = QRangeSlider()
        self.range_slider.rangeChanged.connect(self._on_range_slider_changed)
        self.range_slider.sliderReleased.connect(self._on_range_slider_released)
        layout.addWidget(self.range_slider)

        # Single slider
        self.single_slider = QSlider(Qt.Horizontal)
        self.single_slider.valueChanged.connect(self._on_single_slider_value_changed)
        self.single_slider.sliderReleased.connect(self._on_single_slider_released)
        layout.addWidget(self.single_slider)

        # Max / Single spinbox
        self.spin_max = QDoubleSpinBox()
        self.spin_max.setFixedWidth(65)
        self.spin_max.setStyleSheet("font-size: 11px;")
        self.spin_max.editingFinished.connect(self._on_spin_changed)
        layout.addWidget(self.spin_max)

        self.update_mode(self.current_mode)

    def update_mode(self, mode_id):
        self.current_mode = mode_id
        _, min_val, max_val, suffix = PARAM_DEF[mode_id]
        
        if mode_id == MODE_POS_LIMITS:
            min_val, max_val = get_motor_position_range(self.motor_id)
            
        self.single_slider.setRange(int(min_val * self._slider_scale), int(max_val * self._slider_scale))
        self.range_slider.setRange(min_val, max_val)
        
        for sp in [self.spin_min, self.spin_max]:
            sp.blockSignals(True)
            sp.setRange(min_val, max_val)
            sp.setSuffix(f" {suffix}")
            decimals = 1 if mode_id == MODE_POS_LIMITS else 0
            sp.setDecimals(decimals)
            sp.setSingleStep(100.0 if mode_id == MODE_JOINT_PROTECT else 1.0)
            sp.blockSignals(False)
            
        if mode_id == MODE_JOINT_PROTECT:
            self.spin_min.hide()
            self.range_slider.hide()
            self.single_slider.show()
        else:
            self.spin_min.show()
            self.range_slider.show()
            self.single_slider.hide()

    def set_value_silently(self, max_val, min_val=0.0):
        # We pass max_val first to handle MODE_JOINT_PROTECT easily
        self.spin_min.blockSignals(True)
        self.spin_max.blockSignals(True)
        self.single_slider.blockSignals(True)
        self.range_slider.blockSignals(True)
        
        if self.current_mode == MODE_JOINT_PROTECT:    
            self.spin_max.setValue(max_val)
            self.single_slider.setValue(int(max_val * self._slider_scale))
        else:
            self.spin_min.setValue(min_val)
            self.spin_max.setValue(max_val)
            self.range_slider.setValues(min_val, max_val)
            
        self.spin_min.blockSignals(False)
        self.spin_max.blockSignals(False)
        self.single_slider.blockSignals(False)
        self.range_slider.blockSignals(False)

    def _on_single_slider_value_changed(self, val):
        if not self.spin_max.signalsBlocked():
            self.spin_max.blockSignals(True)
            self.spin_max.setValue(val / self._slider_scale)
            self.spin_max.blockSignals(False)

    def _on_single_slider_released(self):
        val = self.single_slider.value() / self._slider_scale
        self.spin_max.blockSignals(True)
        self.spin_max.setValue(val)
        self.spin_max.blockSignals(False)
        self.set_callback(self.motor_id, self.current_mode, val, 0.0)

    def _on_range_slider_changed(self, low, high):
        self.spin_min.blockSignals(True)
        self.spin_max.blockSignals(True)
        self.spin_min.setValue(low)
        self.spin_max.setValue(high)
        self.spin_min.blockSignals(False)
        self.spin_max.blockSignals(False)

    def _on_range_slider_released(self):
        low, high = self.range_slider.getValues()
        self.set_callback(self.motor_id, self.current_mode, high, low)

    def _on_spin_changed(self):
        if self.current_mode == MODE_JOINT_PROTECT:
            val = self.spin_max.value()
            self.single_slider.blockSignals(True)
            self.single_slider.setValue(int(val * self._slider_scale))
            self.single_slider.blockSignals(False)
            self.set_callback(self.motor_id, self.current_mode, val, 0.0)
        else:
            low = self.spin_min.value()
            high = self.spin_max.value()
            if low > high:
                if self.sender() == self.spin_min:
                    low = high
                    self.spin_min.setValue(low)
                else:
                    high = low
                    self.spin_max.setValue(high)

            self.range_slider.blockSignals(True)
            self.range_slider.setValues(low, high)
            self.range_slider.blockSignals(False)
            self.set_callback(self.motor_id, self.current_mode, high, low)

class V3ConfigFingerGroup(QGroupBox):
    def __init__(self, name, motor_ids, set_callback):
        super().__init__(name)
        self.motor_ids = motor_ids
        self.sliders = {}
        
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                margin-top: 8px;
                padding: 12px 8px 8px 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {COLORS['primary']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        
        for motor_id in motor_ids:
            slider = V3ConfigSlider(motor_id, set_callback)
            layout.addWidget(slider)
            self.sliders[motor_id] = slider
            
    def update_mode(self, mode):
        for s in self.sliders.values():
            s.update_mode(mode)


class V3MotorConfigPanel(QWidget):
    """Separate panel to configure Revo3 motor protection & limits"""
    def __init__(self):
        super().__init__()
        self.device = None
        self.slave_id = 1
        self.shared_data = None
        
        self.current_mode = MODE_JOINT_PROTECT
        self.finger_groups = {}
        self.all_sliders = {}
        
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self._on_refresh_data)
        self.auto_refresh_timer.setInterval(3000)  # 3 seconds as requested
        
        self._setup_ui()
        
    def set_device(self, device, slave_id, device_info, protocol, shared_data=None):
        self.device = device
        self.slave_id = slave_id
        if self.auto_refresh_cb.isChecked():
            self.auto_refresh_timer.start()
        self._on_refresh_data()
        
    def clear_device(self):
        self.device = None
        self.auto_refresh_timer.stop()

    def update_texts(self):
        pass # Handle any translations later

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Top Control Bar ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Parameter Type:"))
        
        self.mode_combo = QComboBox()
        for mode_id, data in PARAM_DEF.items():
            self.mode_combo.addItem(data[0], mode_id)
        self.mode_combo.setCurrentIndex(0) # Default to Position Limits
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self.mode_combo)
        
        self.refresh_btn = QPushButton(tr("v3_read_parameters"))
        self.refresh_btn.setFixedWidth(120)
        self.refresh_btn.clicked.connect(self._on_refresh_data)
        top_bar.addWidget(self.refresh_btn)
        
        self.auto_refresh_cb = QCheckBox(tr("v3_auto_refresh"))
        self.auto_refresh_cb.setChecked(True)
        self.auto_refresh_cb.stateChanged.connect(self._on_auto_refresh_changed)
        top_bar.addWidget(self.auto_refresh_cb)
        
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # --- 2x3 Grid layout for joints ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        container.setLayout(grid)
        
        finger_names = get_v3_finger_names()
        finger_motors = get_v3_finger_motors()
        
        for i, name in enumerate(finger_names):
            motor_ids = finger_motors[name]
            group = V3ConfigFingerGroup(name, motor_ids, self._on_set_single_parameter)
            self.finger_groups[name] = group
            for m, s in group.sliders.items():
                self.all_sliders[m] = s
                
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # Build 6th slot container (row 1, col 2)
        slot6_container = QWidget()
        slot6_layout = QVBoxLayout(slot6_container)
        slot6_layout.setContentsMargins(0, 0, 0, 0)
        slot6_layout.setSpacing(6)

        # Turbo Mode Group
        self.turbo_group = QGroupBox(tr("turbo_mode"))
        self.turbo_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                margin-top: 8px;
                padding: 12px 8px 8px 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {COLORS['primary']};
            }}
        """)
        t_layout = QVBoxLayout(self.turbo_group)
        t_layout.setSpacing(8)
        
        turbo_row1 = QHBoxLayout()
        self.turbo_check = QCheckBox(tr("enable_turbo"))
        self.turbo_check.stateChanged.connect(self._on_turbo_changed)
        turbo_row1.addWidget(self.turbo_check)
        turbo_row1.addStretch()
        t_layout.addLayout(turbo_row1)
        
        turbo_row2 = QHBoxLayout()
        turbo_row2.setContentsMargins(0, 0, 0, 0)
        
        lbl_i = QLabel(tr("turbo_interval") + ":")
        lbl_i.setStyleSheet("font-size: 12px;")
        turbo_row2.addWidget(lbl_i)
        
        self.turbo_interval_spin = QSpinBox()
        self.turbo_interval_spin.setRange(0, 10000)
        self.turbo_interval_spin.setValue(1000)
        self.turbo_interval_spin.setFixedWidth(65)
        turbo_row2.addWidget(self.turbo_interval_spin)
        
        lbl_d = QLabel(tr("turbo_duration") + ":")
        lbl_d.setStyleSheet("font-size: 12px;")
        turbo_row2.addWidget(lbl_d)
        
        self.turbo_duration_spin = QSpinBox()
        self.turbo_duration_spin.setRange(0, 10000)
        self.turbo_duration_spin.setValue(500)
        self.turbo_duration_spin.setFixedWidth(65)
        turbo_row2.addWidget(self.turbo_duration_spin)
        
        self.turbo_apply_btn = QPushButton(tr("btn_apply"))
        self.turbo_apply_btn.setFixedWidth(50)
        self.turbo_apply_btn.clicked.connect(self._apply_turbo_config)
        turbo_row2.addWidget(self.turbo_apply_btn)
        
        turbo_row2.addStretch()
        t_layout.addLayout(turbo_row2)
        slot6_layout.addWidget(self.turbo_group)

        # Build Global Settings for the 6th slot (row 1, col 2)
        self.global_group = QGroupBox(tr("v3_global_settings"))
        self.global_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                margin-top: 8px;
                padding: 16px 8px 12px 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {COLORS['primary']};
            }}
        """)
        g_layout = QVBoxLayout(self.global_group)
        g_layout.setSpacing(12)

        def add_global_row(label, spin, btn, action):
            row_w = QHBoxLayout()
            row_w.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setFixedWidth(160)
            lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
            row_w.addWidget(lbl)
            spin.setFixedWidth(110)
            spin.setStyleSheet("font-size: 13px;")
            row_w.addWidget(spin)
            btn.setFixedWidth(60)
            btn.clicked.connect(action)
            row_w.addWidget(btn)
            row_w.addStretch()
            g_layout.addLayout(row_w)

        self.global_spin = QDoubleSpinBox()
        self.global_spin.setRange(0, 5000)
        self.global_spin.setSingleStep(100)
        self.global_spin.setSuffix(" mA")
        self.global_spin.setDecimals(1)
        self.global_set_btn = QPushButton(tr("btn_set"))
        add_global_row(tr("v3_global_protect_current"), self.global_spin, self.global_set_btn, self._on_set_global)

        self.calib_current_spin = QDoubleSpinBox()
        self.calib_current_spin.setRange(0.0, 1024.0)
        self.calib_current_spin.setSingleStep(10.0)
        self.calib_current_spin.setSuffix(" mA")
        self.calib_current_spin.setDecimals(1)
        self.calib_current_btn = QPushButton(tr("btn_set"))
        add_global_row(tr("v3_calibration_current"), self.calib_current_spin, self.calib_current_btn, self._on_set_calibration_current)

        self.max_current_spin = QDoubleSpinBox()
        self.max_current_spin.setRange(0.0, 1024.0)
        self.max_current_spin.setSingleStep(10.0)
        self.max_current_spin.setSuffix(" mA")
        self.max_current_spin.setDecimals(1)
        self.max_current_btn = QPushButton(tr("btn_set"))
        add_global_row(tr("v3_max_continuous_current"), self.max_current_spin, self.max_current_btn, self._on_set_max_continuous_current)

        g_layout.addStretch()
        slot6_layout.addWidget(self.global_group)
        slot6_layout.addStretch()
        grid.addWidget(slot6_container, 1, 2)
            
        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)
            
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _on_auto_refresh_changed(self, state):
        if state == Qt.Checked and self.device:
            self.auto_refresh_timer.start()
        else:
            self.auto_refresh_timer.stop()

    def _on_mode_changed(self, idx):
        self.current_mode = self.mode_combo.itemData(idx)
        for group in self.finger_groups.values():
            group.update_mode(self.current_mode)
        self._on_refresh_data()

    def _on_turbo_changed(self, state):
        enabled = state == Qt.Checked
        if not self.device:
            return
        run_async(lambda: self.device.set_turbo_mode_enabled(self.slave_id, enabled))
        print(f"[Config] Turbo mode {'enabled' if enabled else 'disabled'}")

    def _apply_turbo_config(self):
        if not self.device:
            return
        interval = self.turbo_interval_spin.value()
        duration = self.turbo_duration_spin.value()
        config = sdk.TurboConfig(interval, duration)
        run_async(lambda: self.device.set_turbo_config(self.slave_id, config))
        print(f"[Config] Turbo config applied: interval={interval}ms, duration={duration}ms")

    def _on_set_global(self):
        if not self.device:
            return
        val = self.global_spin.value()
        run_async(lambda: self.device.revo3_set_global_protect_current(self.slave_id, val))
        print(f"[Config] Global protect current set to {val} mA")

    def _on_set_calibration_current(self):
        if not self.device:
            return
        val = self.calib_current_spin.value()
        run_async(lambda: self.device.v3_set_calibration_current(self.slave_id, val))
        print(f"[Config] Calibration current set to {val} mA")

    def _on_set_max_continuous_current(self):
        if not self.device:
            return
        val = self.max_current_spin.value()
        run_async(lambda: self.device.v3_set_max_continuous_current(self.slave_id, val))
        print(f"[Config] Max continuous current set to {val} mA")

    def _on_set_single_parameter(self, motor_id, mode, val, sister_val):
        if not self.device:
            return
            
        if mode == MODE_JOINT_PROTECT:
            run_async(lambda: self.device.revo3_set_joint_protect_current(self.slave_id, motor_id, val))
        elif mode == MODE_POS_LIMITS:
            run_async(lambda: self.device.revo3_set_joint_position_limits(
                self.slave_id, motor_id, int(sister_val * 100), int(val * 100)))
        elif mode == MODE_SPEED_LIMITS:
            run_async(lambda: self.device.revo3_set_joint_speed_limits(
                self.slave_id, motor_id, int(sister_val), int(val)))

    def _on_refresh_data(self):
        if not self.device:
            return

        # Refresh global values unconditionally
        globals_data = run_async(lambda: asyncio.gather(
            self.device.revo3_get_global_protect_current(self.slave_id),
            # Add read values for calibration and max current once available in rust bindings.
            # Currently API does not provide getter for those. We'll refresh protect current:
            return_exceptions=True
        ))
        if globals_data and not isinstance(globals_data[0], Exception):
            if globals_data[0] is not None:
                self.global_spin.setValue(globals_data[0])

        if self.current_mode == MODE_JOINT_PROTECT:
            vals = run_async(lambda: self.device.revo3_get_all_joint_protect_currents(self.slave_id))
            if vals and len(vals) >= 21:
                for i in range(21):
                    if i in self.all_sliders:
                        self.all_sliders[i].set_value_silently(vals[i])
                        
        elif self.current_mode == MODE_POS_LIMITS:
            res = run_async(lambda: self.device.revo3_get_all_joint_position_limits(self.slave_id))
            if res and len(res) == 2 and len(res[0]) >= 21:
                min_pos, max_pos = res
                for i in range(21):
                    if i in self.all_sliders:
                        self.all_sliders[i].set_value_silently(max_pos[i], min_pos[i])
                            
        elif self.current_mode == MODE_SPEED_LIMITS:
            res = run_async(lambda: self.device.revo3_get_all_joint_speed_limits(self.slave_id))
            if res and len(res) == 2 and len(res[0]) >= 21:
                min_spd, max_spd = res
                for i in range(21):
                    if i in self.all_sliders:
                        self.all_sliders[i].set_value_silently(max_spd[i], min_spd[i])
