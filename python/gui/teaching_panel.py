"""Teaching Panel - Record and Playback Hand Movements (GUI)

Adapted from revo3/revo3_teaching.py for PySide6 GUI integration.

Workflow:
  1. RECORD: Enter teaching mode (zero torque), record motor positions via QTimer.
  2. STOP:   Exit teaching mode, restore control, save trajectory.
  3. PLAY:   Replay recorded trajectory with position control via QTimer.

Key differences from CLI version:
  - Uses QTimer instead of asyncio loops for recording/playback.
  - Reads motor data from SharedDataManager's revo3_motor_buffer.
  - All async SDK calls use run_async() wrapper (same as motor_control_panel_revo3).
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox,
    QFileDialog, QTextEdit, QProgressBar, QFrame,
    QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QTimer

from .i18n import tr
from .styles import COLORS

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

if TYPE_CHECKING:
    from .shared_data import SharedDataManager


# Motor group labels (same as revo3_teaching.py)
MOTOR_LABELS = {
    "Pinky":  [0, 1, 2, 3],
    "Ring":   [4, 5, 6, 7],
    "Middle": [8, 9, 10, 11],
    "Index":  [12, 13, 14, 15],
    "Thumb":  [16, 17, 18, 19, 20],
}

# Import constants from constants.py
from .constants import REVO3_MOTOR_COUNT

DEFAULT_RECORD_FREQ = 100    # Hz
DEFAULT_PLAYBACK_SPEED = 1.0
DEFAULT_LOOP_COUNT = 1


def _get_motor_count():
    return REVO3_MOTOR_COUNT


def run_async(coro_fn):
    """Run async coroutine from Qt callbacks (same pattern as motor_control_panel_revo3)."""
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


# =============================================================================
# Trajectory Data (same as revo3_teaching.py)
# =============================================================================

class Trajectory:
    """Stores a sequence of timestamped motor position snapshots."""

    def __init__(self):
        self.frames = []       # List of (timestamp_sec, positions[N])
        self.start_time = None

    def add_frame(self, positions):
        """Add a position snapshot with relative timestamp."""
        now = time.perf_counter()
        if self.start_time is None:
            self.start_time = now
        relative_t = now - self.start_time
        self.frames.append((relative_t, list(positions)))

    @property
    def duration(self):
        if not self.frames:
            return 0.0
        return self.frames[-1][0]

    @property
    def frame_count(self):
        return len(self.frames)

    def save(self, filepath):
        """Save trajectory to JSON file."""
        actual_motor_count = len(self.frames[0][1]) if self.frames else 0
        data = {
            "motor_count": actual_motor_count,
            "frame_count": len(self.frames),
            "duration_sec": self.duration,
            "frames": [
                {"t": round(t, 4), "pos": [round(p, 2) for p in pos]}
                for t, pos in self.frames
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(filepath):
        """Load trajectory from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        traj = Trajectory()
        traj.start_time = 0
        for frame in data["frames"]:
            traj.frames.append((frame["t"], frame["pos"]))
        return traj

    def summary_text(self):
        """Return trajectory summary as text lines."""
        if not self.frames:
            return "(empty trajectory)"
        lines = []
        lines.append(f"Frames: {self.frame_count}")
        lines.append(f"Duration: {self.duration:.2f}s")
        avg_freq = self.frame_count / self.duration if self.duration > 0 else 0
        lines.append(f"Avg frequency: {avg_freq:.1f} Hz")

        # Show position range per finger group
        all_pos = [pos for _, pos in self.frames]
        pos_len = len(all_pos[0]) if all_pos else 0
        for name, motor_ids in MOTOR_LABELS.items():
            valid_ids = [mid for mid in motor_ids if mid < pos_len]
            if not valid_ids:
                continue
            mins = [min(frame[mid] for frame in all_pos) for mid in valid_ids]
            maxs = [max(frame[mid] for frame in all_pos) for mid in valid_ids]
            ranges = [f"M{mid}:[{mn:.0f}°,{mx:.0f}°]" for mid, mn, mx in zip(valid_ids, mins, maxs)]
            lines.append(f"  {name:6s}: {', '.join(ranges)}")
        return "\n".join(lines)


# =============================================================================
# Teaching Mode Functions (adapted from revo3_teaching.py)
# =============================================================================

def enter_teaching_mode(device, slave_id):
    """Enter teaching mode - hand becomes compliant (zero torque)."""
    # Set Impedance mode and zero stiffness
    try:
        run_async(lambda: device.revo3_set_teaching_mode(slave_id, True))
    except Exception as e:
        print(f"[Teaching] Enter mode failed: {e}")


def exit_teaching_mode(device, slave_id, restore_positions=None):
    """Exit teaching mode and restore motor control."""
    try:
        run_async(lambda: device.revo3_set_teaching_mode(slave_id, False))
        time.sleep(0.1)
    except Exception as e:
        print(f"[Teaching] Restore position mode skipped: {e}")

    if restore_positions is not None:
        run_async(lambda: device.revo3_set_all_motor_positions(slave_id, restore_positions))
    else:
        target = [0.0] * _get_motor_count()
        run_async(lambda: device.revo3_set_all_motor_positions(slave_id, target))

    time.sleep(0.3)


# =============================================================================
# Teaching Panel Widget
# =============================================================================

class TeachingPanel(QWidget):
    """Teaching mode panel for recording and playing back hand trajectories."""

    # States
    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_PLAYING = "playing"

    def __init__(self):
        super().__init__()
        self.shared_data: Optional['SharedDataManager'] = None
        self._device = None
        self._slave_id = 1
        self._device_info = None

        self._state = self.STATE_IDLE
        self._trajectory: Optional[Trajectory] = None
        self._initial_positions: Optional[List[float]] = None

        # Recording state
        self._record_timer: Optional[QTimer] = None
        self._record_frame_count = 0
        self._record_start_time = 0.0

        # Playback state
        self._playback_timer: Optional[QTimer] = None
        self._playback_frame_idx = 0
        self._playback_start_time = 0.0
        self._playback_current_loop = 0

        self._setup_ui()
        self.update_texts()

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
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        self.setLayout(layout)

        # === Top: Controls ===
        controls_group = QGroupBox(tr("teaching_controls"))
        controls_layout = QGridLayout()
        controls_layout.setSpacing(8)
        controls_group.setLayout(controls_layout)

        # Row 0: Recording controls
        self.record_btn = QPushButton("🔴 " + tr("teaching_record"))
        self.record_btn.setMinimumHeight(40)
        self.record_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold;
                background-color: #e74c3c; color: white;
                border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.record_btn.clicked.connect(self._on_record)
        controls_layout.addWidget(self.record_btn, 0, 0)

        self.stop_btn = QPushButton("⏹ " + tr("teaching_stop"))
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold;
                background-color: #7f8c8d; color: white;
                border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #636e72; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        controls_layout.addWidget(self.stop_btn, 0, 1)

        self.play_btn = QPushButton("▶ " + tr("teaching_play"))
        self.play_btn.setMinimumHeight(40)
        self.play_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold;
                background-color: #27ae60; color: white;
                border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #219a52; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._on_play)
        controls_layout.addWidget(self.play_btn, 0, 2)

        # Row 1: Parameters
        param_layout = QHBoxLayout()

        param_layout.addWidget(QLabel(tr("teaching_record_freq")))
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(10, 500)
        self.freq_spin.setValue(DEFAULT_RECORD_FREQ)
        self.freq_spin.setSuffix(" Hz")
        self.freq_spin.setFixedWidth(100)
        param_layout.addWidget(self.freq_spin)

        param_layout.addSpacing(16)

        param_layout.addWidget(QLabel(tr("teaching_playback_speed")))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 5.0)
        self.speed_spin.setValue(DEFAULT_PLAYBACK_SPEED)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setFixedWidth(90)
        param_layout.addWidget(self.speed_spin)

        param_layout.addSpacing(16)

        param_layout.addWidget(QLabel(tr("teaching_loop_count")))
        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(1, 100)
        self.loop_spin.setValue(DEFAULT_LOOP_COUNT)
        self.loop_spin.setFixedWidth(70)
        param_layout.addWidget(self.loop_spin)

        param_layout.addStretch()
        controls_layout.addLayout(param_layout, 1, 0, 1, 3)

        # Row 2: File operations
        file_layout = QHBoxLayout()

        self.save_btn = QPushButton("💾 " + tr("teaching_save"))
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        file_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("📂 " + tr("teaching_load"))
        self.load_btn.clicked.connect(self._on_load)
        file_layout.addWidget(self.load_btn)

        self.file_label = QLabel("")
        self.file_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-style: italic;")
        file_layout.addWidget(self.file_label)

        file_layout.addStretch()
        controls_layout.addLayout(file_layout, 2, 0, 1, 3)

        layout.addWidget(controls_group)

        # === Middle: Status ===
        status_group = QGroupBox(tr("teaching_status"))
        status_layout = QVBoxLayout()
        status_group.setLayout(status_layout)

        # State indicator
        state_row = QHBoxLayout()
        self.state_label = QLabel("⚪ " + tr("teaching_state_idle"))
        self.state_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        state_row.addWidget(self.state_label)

        state_row.addStretch()

        self.frame_label = QLabel("")
        self.frame_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        state_row.addWidget(self.frame_label)

        status_layout.addLayout(state_row)

        # Progress bar (for playback)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['primary']};
                border-radius: 3px;
            }}
        """)
        status_layout.addWidget(self.progress_bar)

        layout.addWidget(status_group)

        # === Bottom: Log & Trajectory Summary ===
        bottom_group = QGroupBox(tr("teaching_trajectory_info"))
        bottom_layout = QVBoxLayout()
        bottom_group.setLayout(bottom_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(250)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Courier New';
                font-size: 12px;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        bottom_layout.addWidget(self.log_text)

        layout.addWidget(bottom_group, 1)

    def _log(self, msg):
        """Append a message to the log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # =========================================================================
    # Device Management
    # =========================================================================

    def set_device(self, device, slave_id, device_info, shared_data):
        """Called by MainWindow when device is connected."""
        self._device = device
        self._slave_id = slave_id
        self._device_info = device_info
        self.shared_data = shared_data
        self._update_button_states()
        self._log("✅ Device connected")

    def clear_device(self):
        """Called by MainWindow when device is disconnected."""
        self._stop_all()
        self._device = None
        self._slave_id = 1
        self._device_info = None
        self.shared_data = None
        self._trajectory = None
        self._initial_positions = None
        self.file_label.setText("")
        self._update_button_states()

    # =========================================================================
    # State Management
    # =========================================================================

    def _set_state(self, state):
        """Update state and refresh UI."""
        self._state = state
        if state == self.STATE_IDLE:
            self.state_label.setText("⚪ " + tr("teaching_state_idle"))
            self.state_label.setStyleSheet("font-size: 14px; font-weight: bold;")
            self.progress_bar.setVisible(False)
        elif state == self.STATE_RECORDING:
            self.state_label.setText("🔴 " + tr("teaching_state_recording"))
            self.state_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c;")
            self.progress_bar.setVisible(False)
        elif state == self.STATE_PLAYING:
            self.state_label.setText("▶ " + tr("teaching_state_playing"))
            self.state_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #27ae60;")
            self.progress_bar.setVisible(True)
        self._update_button_states()

    def _update_button_states(self):
        """Enable/disable buttons based on state and device."""
        has_device = self.device is not None
        is_idle = self._state == self.STATE_IDLE
        has_trajectory = self._trajectory is not None and self._trajectory.frame_count >= 2

        self.record_btn.setEnabled(has_device and is_idle)
        self.stop_btn.setEnabled(has_device and not is_idle)
        self.play_btn.setEnabled(has_device and is_idle and has_trajectory)
        self.save_btn.setEnabled(is_idle and has_trajectory)
        self.load_btn.setEnabled(is_idle)
        self.freq_spin.setEnabled(is_idle)
        self.speed_spin.setEnabled(is_idle)
        self.loop_spin.setEnabled(is_idle)

    def _stop_all(self):
        """Stop any active recording or playback."""
        if self._record_timer:
            self._record_timer.stop()
            self._record_timer = None
        if self._playback_timer:
            self._playback_timer.stop()
            self._playback_timer = None

        if self._state == self.STATE_RECORDING and self.device:
            # Exit teaching mode and restore positions
            try:
                exit_teaching_mode(self.device, self.slave_id, self._initial_positions)
            except Exception as e:
                print(f"[Teaching] Error exiting teaching mode: {e}")

        self._set_state(self.STATE_IDLE)

    # =========================================================================
    # Recording
    # =========================================================================

    def _on_record(self):
        """Start recording trajectory."""
        if not self.device or not self.shared_data:
            return

        # Save initial positions
        try:
            latest = None
            if self.shared_data.revo3_motor_buffer:
                latest = self.shared_data.revo3_motor_buffer.peek_latest()
            if latest and hasattr(latest, 'positions'):
                self._initial_positions = list(latest.positions)
                pos_preview = " ".join([f"{self._initial_positions[i]:.1f}" for i in range(min(5, len(self._initial_positions)))])
                self._log(f"Initial positions (M0-4): {pos_preview}")
            else:
                self._log("⚠ No motor data available, using zeros as initial")
                self._initial_positions = [0.0] * _get_motor_count()
        except Exception as e:
            self._log(f"⚠ Failed to read initial positions: {e}")
            self._initial_positions = [0.0] * _get_motor_count()

        # Enter teaching mode
        self._log("Entering teaching mode (zero torque)...")
        try:
            enter_teaching_mode(self.device, self.slave_id)
        except Exception as e:
            self._log(f"❌ Failed to enter teaching mode: {e}")
            return

        self._log("✅ Teaching mode active — move fingers freely")

        # Initialize trajectory and recording
        self._trajectory = Trajectory()
        self._record_frame_count = 0
        self._record_start_time = time.perf_counter()
        self.file_label.setText("[(Unsaved Trajectory)]")

        # Start recording timer
        interval_ms = max(1, int(1000 / self.freq_spin.value()))
        self._record_timer = QTimer()
        self._record_timer.timeout.connect(self._on_record_tick)
        self._record_timer.start(interval_ms)

        self._set_state(self.STATE_RECORDING)
        self._log(f"📝 Recording at {self.freq_spin.value()} Hz...")

    def _on_record_tick(self):
        """Called by timer to capture one frame."""
        if not self.shared_data or not self.shared_data.revo3_motor_buffer:
            return

        latest = self.shared_data.revo3_motor_buffer.peek_latest()
        if latest and hasattr(latest, 'positions'):
            positions = list(latest.positions)
            self._trajectory.add_frame(positions)
            self._record_frame_count += 1

            # Update UI every ~0.5 seconds
            elapsed = time.perf_counter() - self._record_start_time
            if self._record_frame_count % max(1, self.freq_spin.value() // 2) == 0:
                actual_freq = self._record_frame_count / elapsed if elapsed > 0 else 0
                pos_preview = " ".join([f"{positions[i]:.1f}" for i in range(min(5, len(positions)))])
                self.frame_label.setText(
                    f"{self._record_frame_count} frames | {elapsed:.1f}s | {actual_freq:.0f}Hz | M0-4: {pos_preview}"
                )

    def _on_stop(self):
        """Stop recording or playback."""
        if self._state == self.STATE_RECORDING:
            # Stop recording timer
            if self._record_timer:
                self._record_timer.stop()
                self._record_timer = None

            # Exit teaching mode
            self._log("Exiting teaching mode...")
            try:
                exit_teaching_mode(self.device, self.slave_id, self._initial_positions)
                self._log("✅ Motor control restored")
            except Exception as e:
                self._log(f"⚠ Error restoring control: {e}")

            # Show summary
            if self._trajectory and self._trajectory.frame_count > 0:
                self._log(f"⏹ Recording stopped: {self._trajectory.frame_count} frames, "
                         f"{self._trajectory.duration:.2f}s")
                self._log(self._trajectory.summary_text())
            else:
                self._log("⏹ Recording stopped (no frames captured)")

        elif self._state == self.STATE_PLAYING:
            # Stop playback timer
            if self._playback_timer:
                self._playback_timer.stop()
                self._playback_timer = None
            self._log(f"⏹ Playback stopped at frame {self._playback_frame_idx}")

        self._set_state(self.STATE_IDLE)
        self.frame_label.setText("")

    # =========================================================================
    # Playback
    # =========================================================================

    def _on_play(self):
        """Start trajectory playback."""
        if not self.device or not self._trajectory or self._trajectory.frame_count < 2:
            return

        speed = self.speed_spin.value()
        self._playback_current_loop = 0
        total_loops = self.loop_spin.value()

        self._log(f"▶ Playback: {self._trajectory.frame_count} frames, "
                 f"{self._trajectory.duration:.2f}s at {speed:.1f}x speed, "
                 f"{total_loops} loop(s)")

        # Initialize rigidity before playback
        self._prepare_playback()

        # Start playback
        self._start_playback_loop()

    def _prepare_playback(self):
        """Set up motor control mode for playback."""
        try:
            run_async(lambda: self.device.revo3_set_teaching_mode(self.slave_id, False))
            time.sleep(0.1)
        except Exception:
            pass

    def _start_playback_loop(self):
        """Start one playback loop."""
        total_loops = self.loop_spin.value()
        self._playback_current_loop += 1

        if self._playback_current_loop > total_loops:
            # All loops done
            self._log("✅ Playback complete!")
            self._set_state(self.STATE_IDLE)
            self.frame_label.setText("")
            return

        if total_loops > 1:
            self._log(f"  Loop {self._playback_current_loop}/{total_loops}")

        self._playback_frame_idx = 0
        self._playback_start_time = time.perf_counter()

        # Progress bar
        self.progress_bar.setRange(0, self._trajectory.frame_count)
        self.progress_bar.setValue(0)

        # Use a fast timer (1ms) and skip frames by timestamp
        self._playback_timer = QTimer()
        self._playback_timer.timeout.connect(self._on_playback_tick)
        self._playback_timer.start(1)  # 1ms resolution

        self._set_state(self.STATE_PLAYING)

    def _on_playback_tick(self):
        """Called by timer to send position frames based on elapsed time."""
        if not self._trajectory or not self.device:
            self._on_stop()
            return

        speed = self.speed_spin.value()
        elapsed = time.perf_counter() - self._playback_start_time

        # Find the latest frame whose timestamp has passed (skip expired frames)
        send_idx = -1
        while self._playback_frame_idx < self._trajectory.frame_count:
            target_t, _ = self._trajectory.frames[self._playback_frame_idx]
            adjusted_t = target_t / speed
            if elapsed < adjusted_t:
                break
            send_idx = self._playback_frame_idx
            self._playback_frame_idx += 1

        # Send only the latest due frame (skip intermediate ones)
        if send_idx >= 0:
            _, positions = self._trajectory.frames[send_idx]
            pos = list(positions)[:21]

            try:
                run_async(lambda: self.device.revo3_set_all_motor_positions(self.slave_id, pos))
            except Exception as e:
                self._log(f"⚠ Playback error at frame {send_idx}: {e}")

            # Update progress
            self.progress_bar.setValue(self._playback_frame_idx)
            progress_pct = self._playback_frame_idx / self._trajectory.frame_count * 100
            skipped = self._playback_frame_idx - send_idx - 1
            skip_str = f" (skipped {skipped})" if skipped > 0 else ""
            self.frame_label.setText(
                f"Frame {self._playback_frame_idx}/{self._trajectory.frame_count} "
                f"({progress_pct:.0f}%) | {elapsed:.1f}s{skip_str}"
            )

        # Check if playback is done
        if self._playback_frame_idx >= self._trajectory.frame_count:
            if self._playback_timer:
                self._playback_timer.stop()
                self._playback_timer = None

            actual_dur = time.perf_counter() - self._playback_start_time
            target_dur = self._trajectory.duration / speed
            self._log(f"  Loop done: {self._trajectory.frame_count} frames in {actual_dur:.2f}s "
                     f"(target: {target_dur:.2f}s)")

            # Return to initial position
            if self._initial_positions:
                try:
                    run_async(lambda: self.device.revo3_set_all_motor_positions(
                        self.slave_id, self._initial_positions
                    ))
                except Exception:
                    pass
            time.sleep(0.3)

            # Start next loop (or finish)
            self._start_playback_loop()

    # =========================================================================
    # File Operations
    # =========================================================================

    def _on_save(self):
        """Save trajectory to file."""
        if not self._trajectory or self._trajectory.frame_count == 0:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("teaching_save_title"),
            f"trajectory_{int(time.time())}.json",
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                self._trajectory.save(filepath)
                filename = Path(filepath).name
                self.file_label.setText(f"[{filename}]")
                self._log(f"💾 Saved: {filepath} ({self._trajectory.frame_count} frames, "
                         f"{self._trajectory.duration:.2f}s)")
            except Exception as e:
                self._log(f"❌ Save failed: {e}")

    def _on_load(self):
        """Load trajectory from file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, tr("teaching_load_title"),
            "",
            "JSON Files (*.json)"
        )
        if filepath:
            try:
                self._trajectory = Trajectory.load(filepath)
                filename = Path(filepath).name
                self.file_label.setText(f"[{filename}]")
                self._log(f"📂 Loaded: {filename}")
                self._log(self._trajectory.summary_text())
                self._update_button_states()
            except Exception as e:
                self._log(f"❌ Load failed: {e}")

    # =========================================================================
    # I18n
    # =========================================================================

    def update_texts(self):
        """Update all UI texts for language change."""
        # Buttons are updated via state; just re-apply current state text
        self._update_button_labels()

    def _update_button_labels(self):
        """Refresh button labels with current translations."""
        self.record_btn.setText("🔴 " + tr("teaching_record"))
        self.stop_btn.setText("⏹ " + tr("teaching_stop"))
        self.play_btn.setText("▶ " + tr("teaching_play"))
        self.save_btn.setText("💾 " + tr("teaching_save"))
        self.load_btn.setText("📂 " + tr("teaching_load"))
