"""Motor Control Panel V3 - Revo3 (21 motors, float values)

Revo3 has 21 motors (motor_id 0~20) with float-based control:
  - Position: degrees (float)
  - Velocity: float
  - Current: mA (float)
  - MIT: impedance control (position + velocity + current + Kp + Kd per motor)
  - Cartesian: fingertip pose control (x, y, z, rx, ry, rz per finger)

Layout: mode selector switches between motor-level and finger-level views.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QSlider, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QComboBox, QGridLayout,
    QFrame, QSizePolicy, QScrollArea, QStackedWidget, QFormLayout
)
from PySide6.QtCore import Qt, QTimer

from .i18n import tr
from .styles import COLORS

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

# Import constants from constants.py
from .constants import REVO3_MOTOR_COUNT

REVO3_FINGER_COUNT = 5

# Finger -> motor_id mapping (top-to-bottom order per finger)
REVO3_FINGER_MOTORS = {
    "Thumb":  [18, 17, 16, 19, 20],  # 5 DOF (top-down: 18,17,16 + differential 19,20)
    "Index":  [15, 14, 13, 12],      # 4 DOF (top-down)
    "Middle": [11, 10, 9, 8],        # 4 DOF (top-down)
    "Ring":   [7, 6, 5, 4],          # 4 DOF (top-down)
    "Pinky":  [3, 2, 1, 0],          # 4 DOF (top-down)
}

MOTOR_ERROR_BITS = {
    0: "Over Current",
    1: "Over Voltage",
    2: "Under Voltage",
    3: "Over Temp",
    4: "Current Surge",
    8: "Stall",
    11: "Running",
}

def decode_motor_error(err_val) -> list:
    """Decode a motor error integer bitmask into a list of error strings."""
    if err_val == 0:
        return []
    errs = []
    for bit, name in MOTOR_ERROR_BITS.items():
        if (err_val & (1 << bit)) != 0:
            errs.append(name)
    # Check for unknown bits
    known_mask = sum(1 << b for b in MOTOR_ERROR_BITS)
    if (err_val & ~known_mask) != 0:
        errs.append(f"Unknown(0x{err_val:04X})")
    return errs

REVO3_FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

def get_v3_finger_names():
    """Get active finger names based on protocol."""
    return ["Thumb", "Index", "Middle", "Ring", "Pinky"]

def get_v3_finger_motors():
    """Get active finger-motor mapping based on protocol."""
    return REVO3_FINGER_MOTORS

def get_v3_motor_count():
    """Get motor/joint count based on protocol."""
    return REVO3_MOTOR_COUNT

# Cartesian finger names (no wrist - only 5 fingertips)
REVO3_CARTESIAN_FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
REVO3_CARTESIAN_AXES = ["x", "y", "z", "rx", "ry", "rz"]

# Control modes
MODE_POSITION = 0
MODE_VELOCITY = 1
MODE_CURRENT = 2
MODE_IMPEDANCE = 3
MODE_DAMPING = 4
MODE_MIT = 5
MODE_CARTESIAN = 6

# Per-motor position ranges (degrees) based on joint specs
# Pinky  (M0~M3):  Abd [-15,15], MCP [0,90], PIP [0,90], DIP [0,90]
# Ring   (M4~M7):  Abd [-15,15], MCP [0,90], PIP [0,90], DIP [0,90]
# Middle (M8~M11): Abd [-15,15], MCP [0,90], PIP [0,90], DIP [0,90]
# Index  (M12~M15):Abd [-15,15], MCP [0,90], PIP [0,90], DIP [0,90]
# Thumb  (M16~M20):CMC-Rot [0,50], MCP [0,90], IP [0,90], CMC-Abd [0,105], CMC-Flex [0,120]
MOTOR_POSITION_RANGES = {
    # Pinky: [0]=Abd, [1]=MCP, [2]=PIP, [3]=DIP
    0:  (-15.0, 15.0),   # Pinky Abduction
    1:  (0.0, 90.0),     # Pinky MCP
    2:  (0.0, 90.0),     # Pinky PIP
    3:  (0.0, 90.0),     # Pinky DIP
    # Ring: [4]=Abd, [5]=MCP, [6]=PIP, [7]=DIP
    4:  (-15.0, 15.0),   # Ring Abduction
    5:  (0.0, 90.0),     # Ring MCP
    6:  (0.0, 90.0),     # Ring PIP
    7:  (0.0, 90.0),     # Ring DIP
    # Middle: [8]=Abd, [9]=MCP, [10]=PIP, [11]=DIP
    8:  (-15.0, 15.0),   # Middle Abduction
    9:  (0.0, 90.0),     # Middle MCP
    10: (0.0, 90.0),     # Middle PIP
    11: (0.0, 90.0),     # Middle DIP
    # Index: [12]=Abd, [13]=MCP, [14]=PIP, [15]=DIP
    12: (-15.0, 15.0),   # Index Abduction
    13: (0.0, 90.0),     # Index MCP
    14: (0.0, 90.0),     # Index PIP
    15: (0.0, 90.0),     # Index DIP
    # Thumb: [16]=CMC-Rot, [17]=MCP, [18]=IP, [19]=CMC-Abd(diff), [20]=CMC-Flex(diff)
    16: (0.0, 50.0),     # Thumb CMC Rotation
    17: (0.0, 90.0),     # Thumb MCP
    18: (0.0, 90.0),     # Thumb IP
    19: (0.0, 105.0),    # Thumb CMC Abduction (differential)
    20: (0.0, 120.0),    # Thumb CMC Flexion (differential)
}

# Joint labels for display (motor_id -> label)
MOTOR_JOINT_LABELS = {
    0: "Abd", 1: "MCP", 2: "PIP", 3: "DIP",       # Pinky
    4: "Abd", 5: "MCP", 6: "PIP", 7: "DIP",       # Ring
    8: "Abd", 9: "MCP", 10: "PIP", 11: "DIP",     # Middle
    12: "Abd", 13: "MCP", 14: "PIP", 15: "DIP",   # Index
    16: "Rot", 17: "MCP", 18: "IP",                # Thumb
    19: "Abd", 20: "Flex",                          # Thumb CMC (diff)
}

def get_motor_position_range(motor_id):
    """Get position range for a specific motor based on product joint specs."""
    return MOTOR_POSITION_RANGES.get(motor_id, (-90.0, 90.0))

# Joint type classification: flexion joints participate in open/close,
# abduction/rotation/wrist joints stay neutral.
# "flexion" joints: MCP, PIP, DIP, IP, Flex
# "neutral" joints: Abd, Rot, Wrist
FLEXION_MOTOR_IDS = {
    1, 2, 3,          # Pinky MCP, PIP, DIP
    5, 6, 7,          # Ring MCP, PIP, DIP
    9, 10, 11,        # Middle MCP, PIP, DIP
    13, 14, 15,       # Index MCP, PIP, DIP
    17, 18, 20,       # Thumb MCP, IP, CMC-Flex(diff)
}

def get_motor_open_position(motor_id):
    """Get 'open hand' target for a motor. Flexion → 0°, others → 0° (neutral)."""
    return 0.0

def get_motor_close_position(motor_id):
    """Get 'close hand' target for a motor. Flexion → max range, others → 0° (neutral)."""
    if motor_id in FLEXION_MOTOR_IDS:
        _, max_pos = get_motor_position_range(motor_id)
        return max_pos
    return 0.0  # Abduction, rotation, wrist → neutral

# Value ranges per mode (user-facing, used as default; position mode overrides per motor)
MODE_RANGES = {
    MODE_POSITION:  (-30.0, 110.0, 1.0, "°"),  # envelope of all motor ranges
    MODE_VELOCITY:  (0.0, 1000.0, 10.0, ""),
    MODE_CURRENT:   (0.0, 3.0, 0.1, "A"),
    MODE_IMPEDANCE: (0.0, 100.0, 1.0, ""),   # impedance coefficient, param X100
    MODE_DAMPING:   (0.0, 100.0, 1.0, ""),   # damping coefficient, param X100
}

# MIT parameter ranges (position uses per-motor range via get_motor_position_range)
MIT_POS_RANGE = (-30.0, 110.0, 1.0)  # envelope range for UI default
MIT_VEL_RANGE = (0.0, 1000.0, 10.0)
MIT_CUR_RANGE = (0.0, 3.0, 0.1)
MIT_KP_RANGE = (0.0, 5.0, 0.1)
MIT_KD_RANGE = (0.0, 5.0, 0.1)

# Cartesian range: [-100, 100] for all axes
CARTESIAN_RANGE = (-100.0, 100.0, 0.5)


class V3DeviceInfoPanel(QWidget):
    """Device info summary panel for the empty grid slot."""
    def __init__(self):
        super().__init__()
        vl = QVBoxLayout()
        vl.setContentsMargins(4, 8, 4, 4)
        vl.setSpacing(12)
        self.setLayout(vl)

        self.group_dev = QGroupBox(tr("device_info"))
        self.group_motor = QGroupBox(tr("v3_motor_status_info"))

        style = """
            QGroupBox {
                font-weight: bold;
                background-color: #f8f9fa;
                border: 2px solid #5D9CEC;
                border-radius: 6px;
                margin-top: 8px;
                padding: 10px 8px 8px 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background-color: transparent;
                color: #5D9CEC;
                font-size: 14px;
            }
            QLabel { font-size: 14px; }
        """
        self.group_dev.setStyleSheet(style)
        self.group_motor.setStyleSheet(style.replace("#5D9CEC", "#e67e22").replace("#f8f9fa", "#fdfbf7"))

        # Device info UI
        l_dev = QVBoxLayout()
        self.lbl_hw = QLabel("HW: --")
        self.lbl_fw = QLabel("FW: --")
        self.lbl_sn = QLabel("SN: --")
        self.lbl_online = QLabel("Online: --")
        for lbl in [self.lbl_hw, self.lbl_fw, self.lbl_sn, self.lbl_online]:
            l_dev.addWidget(lbl)
        self.group_dev.setLayout(l_dev)

        # Motor status UI
        l_motor = QVBoxLayout()
        self.lbl_temp = QLabel("Temp: --")
        self.lbl_errors = QLabel("Errors: --")
        self.lbl_last_update = QLabel("")
        self.lbl_last_update.setStyleSheet("color: #999; font-size: 10px;")
        for lbl in [self.lbl_temp, self.lbl_errors, self.lbl_last_update]:
            l_motor.addWidget(lbl)
        self.group_motor.setLayout(l_motor)

        vl.addWidget(self.group_dev)
        vl.addWidget(self.group_motor)
        vl.addStretch()

    def update_info(self, hw=None, fw=None, sn=None, online=None,
                    temps=None, errors=None):
        """Update all device info labels."""
        import time
        if hw is not None:
            self.lbl_hw.setText(f"HW: {hw}")
        if fw is not None:
            self.lbl_fw.setText(f"FW: {fw}")
        if sn is not None:
            self.lbl_sn.setText(f"SN: {sn if sn else '(empty)'}")
        if online is not None:
            total = 21
            cnt = bin(online).count('1')
            offline = [f"M{i}" for i in range(total) if not (online & (1 << i))]
            if offline:
                self.lbl_online.setText(f"Online: ⚠ {cnt}/{total}")
                self.lbl_online.setToolTip(f"Offline: {', '.join(offline)}")
                self.lbl_online.setStyleSheet("color: #e74c3c; font-weight: bold;")
            else:
                self.lbl_online.setText(f"Online: ✅ {cnt}/{total}")
                self.lbl_online.setToolTip("")
                self.lbl_online.setStyleSheet("")
        if temps is not None and len(temps) >= 21:
            max_t = max(temps[:21])
            max_i = temps[:21].index(max_t)
            color = "#e74c3c" if max_t >= 60 else ("#e67e22" if max_t >= 45 else "")
            self.lbl_temp.setText(f"Temp: {int(max_t)}°C max (M{max_i})")
            self.lbl_temp.setStyleSheet(f"color: {color};" if color else "")
        if errors is not None:
            err_count = sum(1 for e in errors[:21] if (e & ~(1 << 11)) != 0)
            if err_count:
                self.lbl_errors.setText(f"Errors: ❌ {err_count} motor(s)")
                self.lbl_errors.setStyleSheet("color: #e74c3c; font-weight: bold;")
            else:
                self.lbl_errors.setText("Errors: ✅ None")
                self.lbl_errors.setStyleSheet(f"color: {COLORS['primary']};")
        self.lbl_last_update.setText(f"Updated: {time.strftime('%H:%M:%S')}")

    def clear_info(self):
        """Reset all labels."""
        for lbl in [self.lbl_hw, self.lbl_fw, self.lbl_sn,
                    self.lbl_online, self.lbl_temp, self.lbl_errors]:
            lbl.setText(lbl.text().split(':')[0] + ": --")
            lbl.setStyleSheet("")
        self.lbl_last_update.setText("")


def run_async(coro_fn):
    """Run async coroutine from Qt callbacks (button clicks etc).

    Must pass a zero-arg callable (lambda) that returns a coroutine.
    PyO3 async methods require a *running* event loop at coroutine-creation
    time, so we bootstrap via an async wrapper that creates the coroutine
    inside the already-running loop.

    Example:
        run_async(lambda: device.v3_set_position(slave_id, 0, 45.0))

    Only use for infrequent user actions, NOT for periodic polling
    (SharedDataManager handles that).
    """
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


# ============================================================================
# Motor Slider (shared by Position/Velocity/Current modes)
# ============================================================================

class V3MotorSlider(QWidget):
    """Single motor control: slider + spinbox + status label"""

    def __init__(self, motor_id, send_callback):
        super().__init__()
        self.motor_id = motor_id
        self.send_callback = send_callback
        self._slider_scale = 10
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)

        joint = MOTOR_JOINT_LABELS.get(self.motor_id, "")
        label_text = f"M{self.motor_id:02d} {joint}" if joint else f"M{self.motor_id:02d}"
        self.id_label = QLabel(label_text)
        self.id_label.setFixedWidth(60)
        self.id_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self.id_label)

        self.diag_label = QLabel("")
        self.diag_label.setFixedWidth(55)
        self.diag_label.setAlignment(Qt.AlignCenter)
        self.diag_label.setStyleSheet("font-size: 11px; border-radius: 3px;")
        layout.addWidget(self.diag_label)

        min_pos, max_pos = get_motor_position_range(self.motor_id)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(min_pos * self._slider_scale), int(max_pos * self._slider_scale))
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider, 1)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(min_pos, max_pos)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(1.0)
        self.spin.setFixedWidth(85)
        self.spin.valueChanged.connect(self._on_spin_changed)
        layout.addWidget(self.spin)

        self.status_label = QLabel("--")
        self.status_label.setFixedWidth(55)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def set_mode_range(self, min_val, max_val, step, mode=None):
        if mode == MODE_POSITION:
            min_val, max_val = get_motor_position_range(self.motor_id)
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self._slider_scale = 1 if max_val > 1000 else 10
        self.slider.setRange(int(min_val * self._slider_scale), int(max_val * self._slider_scale))
        self.slider.setValue(0)
        self.spin.setRange(min_val, max_val)
        self.spin.setSingleStep(step)
        self.spin.setValue(0.0)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def _on_slider_changed(self, value):
        float_val = value / self._slider_scale
        self.spin.blockSignals(True)
        self.spin.setValue(float_val)
        self.spin.blockSignals(False)
        self.send_callback(self.motor_id, float_val)

    def _on_spin_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(value * self._slider_scale))
        self.slider.blockSignals(False)
        self.send_callback(self.motor_id, value)

    def update_diagnostics(self, temp, is_online, err_val=0):
        if not is_online:
            self.diag_label.setText("OFF")
            self.diag_label.setStyleSheet("color: white; background-color: #e74c3c; border-radius: 3px; font-size: 9px; padding: 1px;")
            self.diag_label.setToolTip('<span style="font-size:14px;">Offline</span>')
        else:
            real_errs = decode_motor_error(err_val)
            is_error = bool([e for e in real_errs if e != "Running"])

            color = "#27ae60" # Green
            if is_error:
                color = "#e74c3c" # Red
                self.diag_label.setText("⚠")
            else:
                if temp >= 60:
                    color = "#e74c3c" # Red
                elif temp >= 45:
                    color = "#f39c12" # Orange
                self.diag_label.setText(f"{int(temp)}°")

            self.diag_label.setStyleSheet(f"color: white; background-color: {color}; border-radius: 3px; font-size: 9px; padding: 1px;")

            if not real_errs:
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C</span>')
            else:
                err_text = ', '.join(real_errs)
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C<br/>⚠ {err_text}</span>')

    def set_value_silent(self, value):
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(int(value * self._slider_scale))
        self.spin.setValue(value)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def update_status(self, value):
        self.status_label.setText(f"{value:.1f}")


# ============================================================================
# Finger Group (shared by Position/Velocity/Current modes)
# ============================================================================

class V3FingerGroup(QGroupBox):
    """A finger group containing multiple motor sliders"""

    def __init__(self, finger_name, motor_ids, send_callback, finger_action_callback=None):
        super().__init__(finger_name)
        self.finger_name = finger_name
        self.motor_ids = motor_ids
        self.motor_sliders = {}
        self.finger_action_callback = finger_action_callback
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 8)
        self.setLayout(layout)

        # Header row with Open/Close buttons
        header = QHBoxLayout()
        header.setSpacing(4)
        self.open_btn = QPushButton("Open")
        self.open_btn.setFixedHeight(32)
        self.open_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 14px; min-width: 60px;")
        self.open_btn.clicked.connect(self._on_open)
        header.addWidget(self.open_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.setFixedHeight(32)
        self.close_btn.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 14px; min-width: 60px;")
        self.close_btn.clicked.connect(self._on_close)
        header.addWidget(self.close_btn)
        header.addStretch()
        layout.addLayout(header)

        for mid in motor_ids:
            slider = V3MotorSlider(mid, send_callback)
            self.motor_sliders[mid] = slider
            layout.addWidget(slider)

    def _on_open(self):
        if self.finger_action_callback:
            self.finger_action_callback(self.finger_name, "open")

    def _on_close(self):
        if self.finger_action_callback:
            self.finger_action_callback(self.finger_name, "close")

    def set_mode_range(self, min_val, max_val, step, mode=None):
        for slider in self.motor_sliders.values():
            slider.set_mode_range(min_val, max_val, step, mode)
        # Show Open/Close only in Position mode
        visible = (mode == MODE_POSITION) if mode is not None else True
        self.open_btn.setVisible(visible)
        self.close_btn.setVisible(visible)

    def update_motor_status(self, motor_id, value):
        if motor_id in self.motor_sliders:
            self.motor_sliders[motor_id].update_status(value)

    def set_all_values(self, value):
        for slider in self.motor_sliders.values():
            slider.set_value_silent(value)
            slider._on_spin_changed(value)


# ============================================================================
# MIT Motor Row (per motor: position + velocity + current + Kp + Kd)
# ============================================================================

class V3MitMotorRow(QWidget):
    """Single motor MIT control: 5 spinboxes in a row"""

    def __init__(self, motor_id, send_callback):
        super().__init__()
        self.motor_id = motor_id
        self.send_callback = send_callback
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)

        joint = MOTOR_JOINT_LABELS.get(self.motor_id, "")
        label_text = f"M{self.motor_id:02d} {joint}" if joint else f"M{self.motor_id:02d}"
        self.id_label = QLabel(label_text)
        self.id_label.setFixedWidth(60)
        self.id_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(self.id_label)

        self.diag_label = QLabel("")
        self.diag_label.setFixedWidth(26)
        self.diag_label.setAlignment(Qt.AlignCenter)
        self.diag_label.setStyleSheet("font-size: 9px;")
        layout.addWidget(self.diag_label)

        min_pos, max_pos = get_motor_position_range(self.motor_id)

        # Position spinbox (per-motor range)
        self.pos_spin = QDoubleSpinBox()
        self.pos_spin.setRange(min_pos, max_pos)
        self.pos_spin.setDecimals(1)
        self.pos_spin.setSingleStep(MIT_POS_RANGE[2])
        self.pos_spin.setPrefix("P:")
        self.pos_spin.setFixedWidth(80)
        self.pos_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.pos_spin)

        # Velocity spinbox
        self.vel_spin = QDoubleSpinBox()
        self.vel_spin.setRange(*MIT_VEL_RANGE[:2])
        self.vel_spin.setDecimals(1)
        self.vel_spin.setSingleStep(MIT_VEL_RANGE[2])
        self.vel_spin.setPrefix("V:")
        self.vel_spin.setFixedWidth(80)
        self.vel_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.vel_spin)

        # Current spinbox
        self.cur_spin = QDoubleSpinBox()
        self.cur_spin.setRange(*MIT_CUR_RANGE[:2])
        self.cur_spin.setDecimals(2)
        self.cur_spin.setSingleStep(MIT_CUR_RANGE[2])
        self.cur_spin.setPrefix("I:")
        self.cur_spin.setFixedWidth(80)
        self.cur_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.cur_spin)

        # Kp spinbox
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(*MIT_KP_RANGE[:2])
        self.kp_spin.setDecimals(2)
        self.kp_spin.setSingleStep(MIT_KP_RANGE[2])
        self.kp_spin.setPrefix("Kp:")
        self.kp_spin.setFixedWidth(85)
        self.kp_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.kp_spin)

        # Kd spinbox
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(*MIT_KD_RANGE[:2])
        self.kd_spin.setDecimals(2)
        self.kd_spin.setSingleStep(MIT_KD_RANGE[2])
        self.kd_spin.setPrefix("Kd:")
        self.kd_spin.setFixedWidth(85)
        self.kd_spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self.kd_spin)

        # Status label
        self.status_label = QLabel("--")
        self.status_label.setFixedWidth(45)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _on_changed(self, _value):
        """Send MIT command with all 5 params"""
        params = {
            'position': self.pos_spin.value(),
            'velocity': self.vel_spin.value(),
            'current': self.cur_spin.value(),
            'kp': self.kp_spin.value(),
            'kd': self.kd_spin.value(),
        }
        self.send_callback(self.motor_id, params)

    def update_status(self, value):
        self.status_label.setText(f"{value:.1f}")

    def update_diagnostics(self, temp, is_online, err_val=0):
        if not is_online:
            self.diag_label.setText("OFF")
            self.diag_label.setStyleSheet("color: white; background-color: #e74c3c; border-radius: 3px; font-size: 9px; padding: 1px;")
            self.diag_label.setToolTip('<span style="font-size:14px;">Offline</span>')
        else:
            real_errs = decode_motor_error(err_val)
            is_error = bool([e for e in real_errs if e != "Running"])

            color = "#27ae60" # Green
            if is_error:
                color = "#e74c3c" # Red
                self.diag_label.setText("⚠")
            else:
                if temp >= 60:
                    color = "#e74c3c" # Red
                elif temp >= 45:
                    color = "#f39c12" # Orange
                self.diag_label.setText(f"{int(temp)}°")

            self.diag_label.setStyleSheet(f"color: white; background-color: {color}; border-radius: 3px; font-size: 9px; padding: 1px;")

            if not real_errs:
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C</span>')
            else:
                err_text = ', '.join(real_errs)
                self.diag_label.setToolTip(f'<span style="font-size:14px;">Temperature: {temp}°C<br/>⚠ {err_text}</span>')

    def zero_all(self):
        for spin in [self.pos_spin, self.vel_spin, self.cur_spin, self.kp_spin, self.kd_spin]:
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)


# ============================================================================
# MIT Finger Group
# ============================================================================

class V3MitFingerGroup(QGroupBox):
    """MIT finger group with 5-param rows per motor"""

    def __init__(self, finger_name, motor_ids, send_callback):
        super().__init__(finger_name)
        self.motor_ids = motor_ids
        self.motor_rows = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 8)
        self.setLayout(layout)

        for mid in motor_ids:
            row = V3MitMotorRow(mid, send_callback)
            self.motor_rows[mid] = row
            layout.addWidget(row)

    def update_motor_status(self, motor_id, value):
        if motor_id in self.motor_rows:
            self.motor_rows[motor_id].update_status(value)

    def zero_all(self):
        for row in self.motor_rows.values():
            row.zero_all()


# ============================================================================
# Cartesian Finger Control (per finger: x, y, z, rx, ry, rz)
# ============================================================================

class V3CartesianFingerGroup(QGroupBox):
    """Single finger cartesian control: 6 axis spinboxes"""

    def __init__(self, finger_id, finger_name, send_callback):
        super().__init__(finger_name)
        self.finger_id = finger_id
        self.send_callback = send_callback
        self.axis_spins = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QFormLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 8)
        self.setLayout(layout)

        for axis in REVO3_CARTESIAN_AXES:
            spin = QDoubleSpinBox()
            spin.setRange(*CARTESIAN_RANGE[:2])
            spin.setDecimals(2)
            spin.setSingleStep(CARTESIAN_RANGE[2])
            spin.setFixedWidth(100)
            spin.valueChanged.connect(lambda _v, a=axis: self._on_axis_changed(a))
            self.axis_spins[axis] = spin
            layout.addRow(f"{axis}:", spin)

        # Status label
        self.status_label = QLabel("--")
        self.status_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px;")
        layout.addRow("Status:", self.status_label)

    def _on_axis_changed(self, _axis):
        """Send full pose when any axis changes"""
        pose = {a: self.axis_spins[a].value() for a in REVO3_CARTESIAN_AXES}
        self.send_callback(self.finger_id, pose)

    def update_status(self, pose_dict):
        """Update status from read-back pose"""
        parts = [f"{a}:{pose_dict.get(a, 0):.1f}" for a in REVO3_CARTESIAN_AXES]
        self.status_label.setText("  ".join(parts))

    def zero_all(self):
        for spin in self.axis_spins.values():
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)


# ============================================================================
# Main V3 Motor Control Panel
# ============================================================================

class V3MotorControlPanel(QWidget):
    """Motor Control Panel for Revo3 (23 motors, float values)

    Modes:
      - Position / Velocity / Current: per-motor slider control
      - MIT: per-motor impedance control (pos + vel + cur + Kp + Kd)
      - Cartesian: per-finger 6-DoF pose control (x, y, z, rx, ry, rz)
    """

    def __init__(self):
        super().__init__()
        self.shared_data: Optional['SharedDataManager'] = None
        self._device = None
        self._slave_id = 1
        self.current_mode = MODE_POSITION

        self._setup_ui()
        self.update_texts()

        # Timer for reading from shared data (same pattern as V1/V2 motor panel)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_from_shared)
        self.update_timer.setInterval(50)  # 20Hz UI update

        # Timer for periodic diagnostics refresh (5s)
        self.diag_timer = QTimer()
        self.diag_timer.timeout.connect(self._on_read_diagnostics)
        self.diag_timer.setInterval(5000)  # 5 seconds

    @property
    def device(self):
        if self.shared_data and self.shared_data.device:
            return self.shared_data.device
        return self._device

    @property
    def slave_id(self):
        if self.shared_data:
            return self.shared_data.slave_id
        return self._slave_id

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        self.setLayout(layout)

        # Top bar: mode + global buttons
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        self.mode_label = QLabel(tr("mode") + ":")
        top_layout.addWidget(self.mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            tr("mode_position"), tr("mode_speed"), tr("mode_current"),
            "Impedance", "Damping",
            "MIT", "Cartesian"
        ])
        self.mode_combo.setMinimumWidth(120)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_layout.addWidget(self.mode_combo)

        top_layout.addWidget(QLabel("|"))

        self.open_all_btn = QPushButton(tr("btn_open_all"))
        self.open_all_btn.clicked.connect(self._open_all)
        top_layout.addWidget(self.open_all_btn)

        self.close_all_btn = QPushButton(tr("btn_close_all"))
        self.close_all_btn.clicked.connect(self._close_all)
        top_layout.addWidget(self.close_all_btn)

        self.zero_all_btn = QPushButton(tr("btn_zero_all"))
        self.zero_all_btn.clicked.connect(self._zero_all)
        top_layout.addWidget(self.zero_all_btn)

        top_layout.addWidget(QLabel("|"))

        self.btn_read_diag = QPushButton(tr("v3_diag_read"))
        self.btn_read_diag.clicked.connect(self._on_read_diagnostics)
        top_layout.addWidget(self.btn_read_diag)

        self.clear_errors_btn = QPushButton(tr("v3_clear_errors"))
        self.clear_errors_btn.clicked.connect(self._on_clear_motor_errors)
        top_layout.addWidget(self.clear_errors_btn)

        self.manual_calib_btn = QPushButton(tr("v3_manual_calibration"))
        self.manual_calib_btn.clicked.connect(self._on_manual_calibration)
        top_layout.addWidget(self.manual_calib_btn)

        self.reset_finger_btn = QPushButton(tr("v3_reset_finger_defaults"))
        self.reset_finger_btn.clicked.connect(self._on_reset_finger_defaults)
        top_layout.addWidget(self.reset_finger_btn)
        top_layout.addStretch()

        self.lbl_diag_result = QLabel("")
        self.lbl_diag_result.setVisible(False)

        layout.addLayout(top_layout)

        # Top bar 2: Additional settings/actions (moved from bottom settings panel)
        top_layout2 = QHBoxLayout()
        top_layout2.setSpacing(12)

        # --- Quick actions ---
        self.auto_calib_cb = QPushButton(tr("v3_auto_calibration"))
        self.auto_calib_cb.setCheckable(True)
        self.auto_calib_cb.clicked.connect(self._on_set_auto_calibration)
        top_layout2.addWidget(self.auto_calib_cb)

        self.touch_screen_cb = QPushButton(tr("v3_touch_screen"))
        self.touch_screen_cb.setCheckable(True)
        self.touch_screen_cb.clicked.connect(self._on_touch_screen_changed)
        top_layout2.addWidget(self.touch_screen_cb)

        self.buzzer_cb = QPushButton(tr("buzzer"))
        self.buzzer_cb.setCheckable(True)
        self.buzzer_cb.clicked.connect(self._on_buzzer_changed)
        top_layout2.addWidget(self.buzzer_cb)

        self.vibration_cb = QPushButton(tr("vibration"))
        self.vibration_cb.setCheckable(True)
        self.vibration_cb.clicked.connect(self._on_vibration_changed)
        top_layout2.addWidget(self.vibration_cb)

        self.teaching_mode_cb = QPushButton(tr("v3_teaching_mode"))
        self.teaching_mode_cb.setCheckable(True)
        self.teaching_mode_cb.clicked.connect(self._on_teaching_mode_changed)
        top_layout2.addWidget(self.teaching_mode_cb)

        self.software_e_stop_cb = QPushButton(tr("v3_software_e_stop"))
        self.software_e_stop_cb.setCheckable(True)
        self.software_e_stop_cb.clicked.connect(self._on_software_e_stop_changed)
        top_layout2.addWidget(self.software_e_stop_cb)

        self.use_broadcast_id_cb = QPushButton(tr("v3_use_broadcast_id"))
        self.use_broadcast_id_cb.setCheckable(True)
        self.use_broadcast_id_cb.setChecked(True)
        self.use_broadcast_id_cb.clicked.connect(self._on_use_broadcast_id_changed)
        top_layout2.addWidget(self.use_broadcast_id_cb)

        top_layout2.addStretch()
        layout.addLayout(top_layout2)

        # Stacked widget: page 0 = motor sliders, page 1 = MIT, page 2 = Cartesian
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # --- Page 0: Motor sliders (Position/Velocity/Current) ---
        self._build_motor_page()

        # --- Page 1: MIT control ---
        self._build_mit_page()

        # --- Page 2: Cartesian control ---
        self._build_cartesian_page()

    def _build_motor_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        container.setLayout(grid)

        self.finger_groups = {}
        finger_names = get_v3_finger_names()
        finger_motors = get_v3_finger_motors()
        for i, name in enumerate(finger_names):
            motor_ids = finger_motors[name]
            group = V3FingerGroup(name, motor_ids, self._on_motor_value_changed, self._on_finger_action)
            self.finger_groups[name] = group
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # Device info panel in the empty slot (row 1, col 2)
        self.info_panel = V3DeviceInfoPanel()
        grid.addWidget(self.info_panel, 1, 2)

        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

        scroll.setWidget(container)
        self.stack.addWidget(scroll)  # index 0

    def _build_mit_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        container.setLayout(grid)

        self.mit_groups = {}
        finger_names = get_v3_finger_names()
        finger_motors = get_v3_finger_motors()
        for i, name in enumerate(finger_names):
            motor_ids = finger_motors[name]
            group = V3MitFingerGroup(name, motor_ids, self._on_mit_value_changed)
            self.mit_groups[name] = group
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # MIT info panel in the empty slot (row 1, col 2)
        self.mit_info_panel = V3DeviceInfoPanel()
        grid.addWidget(self.mit_info_panel, 1, 2)

        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

        scroll.setWidget(container)
        self.stack.addWidget(scroll)  # index 1

    def _build_cartesian_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        container.setLayout(grid)

        self.cartesian_groups = {}
        for i, name in enumerate(REVO3_CARTESIAN_FINGERS):
            group = V3CartesianFingerGroup(i, name, self._on_cartesian_value_changed)
            self.cartesian_groups[name] = group
            row = 0 if i < 3 else 1
            col = i if i < 3 else i - 3
            grid.addWidget(group, row, col)

        # Cartesian info panel in the empty slot (row 1, col 2)
        self.cart_info_panel = V3DeviceInfoPanel()
        grid.addWidget(self.cart_info_panel, 1, 2)

        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

        scroll.setWidget(container)
        self.stack.addWidget(scroll)  # index 2

    @staticmethod
    def _wrap_layout(layout):
        """Wrap a QLayout in a QWidget for use with QFormLayout"""
        w = QWidget()
        w.setLayout(layout)
        return w

    # ========================================================================
    # Settings callbacks
    # ========================================================================

    def _on_set_auto_calibration(self):
        if not self.device:
            return
        enabled = self.auto_calib_cb.isChecked()
        run_async(lambda: self.device.set_auto_calibration(self.slave_id, enabled))
        print(f"[V3Settings] Auto calibration: {'enabled' if enabled else 'disabled'}")

    def _on_manual_calibration(self):
        if not self.device:
            return
        run_async(lambda: self.device.calibrate_position(self.slave_id))
        print("[V3Settings] Manual calibration triggered")

    def _on_clear_motor_errors(self):
        if not self.device:
            return
        run_async(lambda: self.device.v3_clear_motor_errors(self.slave_id))
        print("[V3Settings] Motor errors cleared")

    def _on_reset_finger_defaults(self):
        if not self.device:
            return
        # reset_default_gesture auto-routes to the correct register for both protocols
        run_async(lambda: self.device.reset_default_gesture(self.slave_id))
        print("[V3Settings] Finger parameters reset to defaults")

    def _on_touch_screen_changed(self):
        if not self.device:
            return
        enabled = self.touch_screen_cb.isChecked()
        run_async(lambda: self.device.revo3_set_touch_screen(self.slave_id, enabled))
        print(f"[V3Settings] Touch screen: {'enabled' if enabled else 'disabled'}")

    def _on_buzzer_changed(self):
        if not self.device:
            return
        enabled = self.buzzer_cb.isChecked()
        run_async(lambda: self.device.set_buzzer_enabled(self.slave_id, enabled))
        print(f"[V3Settings] Buzzer: {'enabled' if enabled else 'disabled'}")

    def _on_vibration_changed(self):
        if not self.device:
            return
        enabled = self.vibration_cb.isChecked()
        run_async(lambda: self.device.set_vibration_enabled(self.slave_id, enabled))
        print(f"[V3Settings] Vibration: {'enabled' if enabled else 'disabled'}")

    def _on_teaching_mode_changed(self):
        if not self.device:
            return
        enabled = self.teaching_mode_cb.isChecked()
        run_async(lambda: self.device.revo3_set_teaching_mode(self.slave_id, enabled))
        print(f"[V3Settings] Teaching mode: {'enabled' if enabled else 'disabled'}")

    def _on_software_e_stop_changed(self):
        if not self.device:
            return
        enabled = self.software_e_stop_cb.isChecked()
        run_async(lambda: self.device.revo3_set_software_e_stop(self.slave_id, enabled))
        print(f"[V3Settings] Software e-stop: {'enabled' if enabled else 'disabled'}")

    def _on_use_broadcast_id_changed(self):
        if not self.device:
            return
        enabled = self.use_broadcast_id_cb.isChecked()
        run_async(lambda: self.device.revo3_set_use_broadcast_id(self.slave_id, enabled))
        print(f"[V3Settings] Use broadcast ID: {'enabled' if enabled else 'disabled'}")

    def _on_read_diagnostics(self):
        async def fetch_diag():
            try:
                hw = await self.device.revo3_get_hardware_version(self.slave_id)
                online = await self.device.revo3_get_motor_online_status(self.slave_id)
                temps = await self.device.revo3_get_all_motor_temperatures(self.slave_id)
                errors = await self.device.v3_get_all_motor_errors(self.slave_id)
                return (True, hw, online, temps, errors)
            except Exception as e:
                return (False, str(e), None, None, None)

        res = run_async(fetch_diag)
        if res:
            success, hw, online, temps, errors = res
            if success:
                total = 21
                online_count = bin(online).count('1')

                # Build offline motor ID list
                offline_ids = [f"M{i:02d}" for i in range(total) if not (online & (1 << i))]
                if offline_ids:
                    online_str = f"⚠ {online_count}/{total} Online  Offline: {', '.join(offline_ids)}"
                else:
                    online_str = f"✅ {online_count}/{total} Online"

                # Find max temperature and which motor
                if temps:
                    max_temp = max(temps[:total])
                    max_mid = temps[:total].index(max_temp)
                    if max_temp >= 60:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d}) ⚠ Overheat!"
                    elif max_temp >= 45:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d}) ⚡Warm"
                    else:
                        temp_str = f"🌡 Max: {int(max_temp)}°C (M{max_mid:02d})"
                else:
                    temp_str = "🌡 N/A"

                # Error code summary (ignore 'Running' bit 11 for global error warning)
                if errors:
                    err_motors = [(i, e) for i, e in enumerate(errors[:total]) if (e & ~(1 << 11)) != 0]
                    if err_motors:
                        err_parts = []
                        for i, e in err_motors[:4]:
                            err_names = [name for name in decode_motor_error(e) if name != "Running"]
                            err_parts.append(f"M{i:02d}={'+'.join(err_names)}")

                        if len(err_motors) > 4:
                            err_parts.append(f"+{len(err_motors)-4} more")
                        err_str = f"❌ ERR: {', '.join(err_parts)}"
                    else:
                        err_str = "✅ No Errors"
                else:
                    err_str = ""

                # Build compact toolbar status (brief indicator)
                issues = []
                if offline_ids:
                    issues.append(f"{len(offline_ids)} offline")
                if errors and err_motors:
                    issues.append(f"{len(err_motors)} err")
                if temps and max(temps[:total]) >= 60:
                    issues.append("overheat")

                if issues:
                    msg = f"⚠ {', '.join(issues)}  |  {temp_str}"
                    self.lbl_diag_result.setStyleSheet("color: #e74c3c; font-weight: bold;")
                else:
                    msg = f"✅ {online_count}/{total} Online  |  {temp_str}"
                    self.lbl_diag_result.setStyleSheet(f"color: {COLORS['primary']};")

                # Update individual motor UI badges
                for group in self.finger_groups.values():
                    for mid, slider in group.motor_sliders.items():
                        is_online = (online & (1 << mid)) != 0
                        temp_val = temps[mid] if mid < len(temps) else 0.0
                        err_val = errors[mid] if errors and mid < len(errors) else 0
                        slider.update_diagnostics(temp_val, is_online, err_val)

                for group in self.mit_groups.values():
                    for mid, row in group.motor_rows.items():
                        is_online = (online & (1 << mid)) != 0
                        temp_val = temps[mid] if mid < len(temps) else 0.0
                        err_val = errors[mid] if errors and mid < len(errors) else 0
                        row.update_diagnostics(temp_val, is_online, err_val)

            else:
                msg = hw  # error message is in hw
                self.lbl_diag_result.setStyleSheet("color: red; font-weight: bold;")

            self.lbl_diag_result.setText(msg)

            # Update info panels on all pages
            for panel in [self.info_panel, self.mit_info_panel, self.cart_info_panel]:
                panel.update_info(hw=hw, online=online, temps=temps, errors=errors)

    def update_texts(self):
        self.mode_label.setText(tr("mode") + ":")
        self.mode_combo.setItemText(0, tr("mode_position"))
        self.mode_combo.setItemText(1, tr("mode_speed"))
        self.mode_combo.setItemText(2, tr("mode_current"))
        self.mode_combo.setItemText(3, "Impedance")
        self.mode_combo.setItemText(4, "Damping")
        self.mode_combo.setItemText(5, "MIT")
        self.mode_combo.setItemText(6, "Cartesian")
        self.open_all_btn.setText(tr("btn_open_all"))
        self.close_all_btn.setText(tr("btn_close_all"))
        self.zero_all_btn.setText(tr("btn_zero_all"))
        self.auto_calib_cb.setText(tr("v3_auto_calibration"))
        self.manual_calib_btn.setText(tr("v3_manual_calibration"))
        self.clear_errors_btn.setText(tr("v3_clear_errors"))
        self.reset_finger_btn.setText(tr("v3_reset_finger_defaults"))
        self.touch_screen_cb.setText(tr("v3_touch_screen"))
        self.buzzer_cb.setText(tr("buzzer"))
        self.vibration_cb.setText(tr("vibration"))
        self.teaching_mode_cb.setText(tr("v3_teaching_mode"))
        self.software_e_stop_cb.setText(tr("v3_software_e_stop"))
        self.use_broadcast_id_cb.setText(tr("v3_use_broadcast_id"))
        self.btn_read_diag.setText(tr("v3_diag_read"))


    # ========================================================================
    # Mode switching
    # ========================================================================

    def _on_mode_changed(self, index):
        self.current_mode = index
        if index <= MODE_DAMPING:
            # Position / Velocity / Current / Impedance / Damping -> motor slider page
            self.stack.setCurrentIndex(0)
            min_val, max_val, step, _ = MODE_RANGES[index]
            for group in self.finger_groups.values():
                group.set_mode_range(min_val, max_val, step, index)
            # Show open/close buttons only in position mode
            self.open_all_btn.setVisible(index == MODE_POSITION)
            self.close_all_btn.setVisible(index == MODE_POSITION)

        elif index == MODE_MIT:
            self.stack.setCurrentIndex(1)
            self.open_all_btn.setVisible(False)
            self.close_all_btn.setVisible(False)
        elif index == MODE_CARTESIAN:
            self.stack.setCurrentIndex(2)
            self.open_all_btn.setVisible(False)
            self.close_all_btn.setVisible(False)

    # ========================================================================
    # Motor value callbacks
    # ========================================================================

    def _on_motor_value_changed(self, motor_id, value):
        device = self.device
        if not device:
            return
        run_async(lambda: self._send_motor_command(motor_id, value))

    async def _send_motor_command(self, motor_id, value):
        try:
            device = self.device
            sid = self.slave_id
            if self.current_mode == MODE_POSITION:
                await device.v3_set_motor_position(sid, motor_id, value)
            elif self.current_mode == MODE_VELOCITY:
                await device.v3_set_motor_velocity(sid, motor_id, value)
            elif self.current_mode == MODE_CURRENT:
                await device.v3_set_motor_current(sid, motor_id, value)
            elif self.current_mode == MODE_IMPEDANCE:
                # V3ControlMode.Impedance=4, param = coefficient × 100
                await device.revo3_single_joint_control(sid, motor_id, 4, int(value * 100))
            elif self.current_mode == MODE_DAMPING:
                # V3ControlMode.Damping=5, param = coefficient × 100
                await device.revo3_single_joint_control(sid, motor_id, 5, int(value * 100))
        except Exception as e:
            print(f"[V3Motor] Send command failed (motor {motor_id}): {e}")

    def _on_mit_value_changed(self, motor_id, params):
        device = self.device
        if not device:
            return
        run_async(lambda: self._send_mit_command(motor_id, params))

    async def _send_mit_command(self, motor_id, params):
        try:
            device = self.device
            sid = self.slave_id
            await device.v3_set_motor_mit(
                sid, motor_id,
                params['position'], params['velocity'], params['current'],
                params['kp'], params['kd']
            )
        except Exception as e:
            print(f"[V3Motor] MIT command failed (motor {motor_id}): {e}")

    def _on_cartesian_value_changed(self, finger_id, pose):
        device = self.device
        if not device:
            return
        run_async(lambda: self._send_cartesian_command(finger_id, pose))

    async def _send_cartesian_command(self, finger_id, pose):
        try:
            device = self.device
            sid = self.slave_id
            fp = sdk.FingertipPose(
                pose['x'], pose['y'], pose['z'],
                pose['rx'], pose['ry'], pose['rz']
            )
            await device.v3_set_fingertip_pose(sid, finger_id, fp)
        except Exception as e:
            print(f"[V3Motor] Cartesian command failed (finger {finger_id}): {e}")


    # ========================================================================
    # Status updates from SharedDataManager (non-blocking buffer reads)
    # ========================================================================

    def _update_status_from_shared(self):
        """Update motor status from shared data manager (non-blocking read)"""
        if not self.shared_data:
            return

        try:
            status = self.shared_data.get_latest_v3_motor()
            if not status:
                return

            # Choose values based on mode
            if self.current_mode == MODE_POSITION:
                values = status.positions
            elif self.current_mode == MODE_VELOCITY:
                values = status.velocities
            elif self.current_mode == MODE_CURRENT:
                values = status.currents
            elif self.current_mode == MODE_MIT:
                values = status.positions  # Show position as primary status for MIT
            elif self.current_mode == MODE_CARTESIAN:
                # Cartesian mode: no motor-level status to show from buffer
                # (fingertip poses would need a separate buffer/API)
                return
            else:
                values = []

            # Update motor slider groups (Position/Velocity/Current)
            if self.current_mode <= MODE_CURRENT:
                for name, group in self.finger_groups.items():
                    for mid in get_v3_finger_motors().get(name, []):
                        if mid < len(values):
                            group.update_motor_status(mid, values[mid])

            # Update MIT groups
            elif self.current_mode == MODE_MIT:
                for name, group in self.mit_groups.items():
                    for mid in get_v3_finger_motors().get(name, []):
                        if mid < len(values):
                            group.update_motor_status(mid, values[mid])

        except Exception as e:
            print(f"[V3Motor] Update status failed: {e}")

    # ========================================================================
    # Device management
    # ========================================================================

    def set_device(self, device, slave_id, device_info=None, shared_data=None):
        """Set device for V3 motor control. Uses SharedDataManager for status polling."""
        self.shared_data = shared_data
        self._device = device
        self._slave_id = slave_id
        if device and shared_data:
            self.update_timer.start()
            # Populate FW/SN from device_info into info panels
            if device_info:
                fw = getattr(device_info, 'firmware_version', '') or ''
                sn = getattr(device_info, 'serial_number', '') or ''
                for panel in [self.info_panel, self.mit_info_panel, self.cart_info_panel]:
                    panel.update_info(fw=fw, sn=sn)
            # Initial diagnostics read + start periodic refresh
            QTimer.singleShot(500, self._on_read_diagnostics)
            self.diag_timer.start()
        else:
            self.update_timer.stop()
            self.diag_timer.stop()

    def clear_device(self):
        self.update_timer.stop()
        self.diag_timer.stop()
        self.shared_data = None
        self._device = None
        # Clear all info panels
        for panel in [self.info_panel, self.mit_info_panel, self.cart_info_panel]:
            panel.clear_info()

    # ========================================================================
    # Global actions
    # ========================================================================

    def _on_finger_action(self, finger_name, action):
        """Handle per-finger Open/Close button click."""
        if self.current_mode != MODE_POSITION or not self.device:
            return
        group = self.finger_groups.get(finger_name)
        if not group:
            return
        # Read current positions as baseline, then modify only this finger
        targets = [0.0] * get_v3_motor_count()
        for name, g in self.finger_groups.items():
            for mid, slider in g.motor_sliders.items():
                targets[mid] = slider.spin.value()
        # Override this finger's targets
        for mid, slider in group.motor_sliders.items():
            if action == "open":
                target = get_motor_open_position(mid)
            else:
                target = get_motor_close_position(mid)
            targets[mid] = target
            slider.set_value_silent(target)
        run_async(lambda: self.device.v3_set_all_motor_positions(self.slave_id, targets))

    def _open_all(self):
        """Open hand: flexion joints → 0°, abduction/rotation → neutral (0°)"""
        if self.current_mode == MODE_POSITION and self.device:
            targets = [0.0] * get_v3_motor_count()
            for name, group in self.finger_groups.items():
                for mid, slider in group.motor_sliders.items():
                    target = get_motor_open_position(mid)
                    targets[mid] = target
                    slider.set_value_silent(target)
            run_async(lambda: self.device.v3_set_all_motor_positions(self.slave_id, targets))

    def _close_all(self):
        """Close hand: flexion joints → max, abduction/rotation → neutral (0°)"""
        if self.current_mode == MODE_POSITION and self.device:
            targets = [0.0] * get_v3_motor_count()
            for name, group in self.finger_groups.items():
                for mid, slider in group.motor_sliders.items():
                    target = get_motor_close_position(mid)
                    targets[mid] = target
                    slider.set_value_silent(target)
            run_async(lambda: self.device.v3_set_all_motor_positions(self.slave_id, targets))

    def _zero_all(self):
        """All controls -> 0"""
        if not self.device:
            return

        if self.current_mode <= MODE_DAMPING:
            targets = [0.0] * get_v3_motor_count()
            for group in self.finger_groups.values():
                for slider in group.motor_sliders.values():
                    slider.set_value_silent(0.0)

            if self.current_mode == MODE_POSITION:
                run_async(lambda: self.device.v3_set_all_motor_positions(self.slave_id, targets))
            elif self.current_mode == MODE_VELOCITY:
                run_async(lambda: self.device.v3_set_all_motor_velocities(self.slave_id, targets))
            elif self.current_mode == MODE_CURRENT:
                run_async(lambda: self.device.v3_set_all_motor_currents(self.slave_id, targets))
            elif self.current_mode in (MODE_IMPEDANCE, MODE_DAMPING):
                mode_val = 4 if self.current_mode == MODE_IMPEDANCE else 5
                params = [0] * 21  # 21 joints, all zero
                run_async(lambda: self.device.revo3_multi_joint_control(self.slave_id, mode_val, params))

        elif self.current_mode == MODE_MIT:
            for group in self.mit_groups.values():
                group.zero_all()
            # Send batch zeroes
            targets = [0.0] * get_v3_motor_count()
            run_async(lambda: self.device.v3_set_all_motor_mit(
                self.slave_id, targets, targets, targets, targets, targets))

        elif self.current_mode == MODE_CARTESIAN:
            for group in self.cartesian_groups.values():
                group.zero_all()
                fp = sdk.FingertipPose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                run_async(lambda: self.device.v3_set_fingertip_pose(self.slave_id, group.finger_id, fp))
