"""Revo3 Timing Test Worker

Handles Revo3 timing tests:
  - Position / Speed / Current tracking modes
  - All-fingers test (21 joints, REVO3_MOTOR_COUNT)
  - Single-finger test (finger group or individual joint, per-joint safe targets)

Joint ID mapping (21 joints, id 0–20):
  Pinky  : 0-3    Ring  : 4-7    Middle: 8-11
  Index  : 12-15  Thumb : 16-20

For Revo1/2 worker see timing_test_worker.py.
"""

import asyncio
import time
import sys
import os
from typing import TYPE_CHECKING
from PySide6.QtCore import QObject, Signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

from .constants import REVO3_MOTOR_COUNT, REVO3_MOTOR_COUNT

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_ALL_FINGERS   = 0
MODE_SINGLE_FINGER = 1

# ── Finger → joint_id mapping (21 joints, 0-20) ────────────────
# Note: joint_id 0-20 matches the Revo3 register layout.
REVO3_FINGER_JOINTS = {
    "Thumb":  [18, 17, 16, 19, 20],   # 5 joints
    "Index":  [15, 14, 13, 12],        # 4 joints
    "Middle": [11, 10,  9,  8],        # 4 joints
    "Ring":   [ 7,  6,  5,  4],        # 4 joints
    "Pinky":  [ 3,  2,  1,  0],        # 4 joints
}

REVO3_FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

# REVO3 single finger options (for UI)
REVO3_SINGLE_FINGER_OPTIONS = [
    ("Thumb",  REVO3_FINGER_JOINTS["Thumb"]),
    ("Index",  REVO3_FINGER_JOINTS["Index"]),
    ("Middle", REVO3_FINGER_JOINTS["Middle"]),
    ("Ring",   REVO3_FINGER_JOINTS["Ring"]),
    ("Pinky",  REVO3_FINGER_JOINTS["Pinky"]),
]

# REVO3 single joint options (for UI): only joints 0-20
REVO3_SINGLE_JOINT_OPTIONS = [(f"M{i}", [i]) for i in range(REVO3_MOTOR_COUNT)]

# ── Position constants ────────────────────────────────────────────────────────
REVO3_OPEN_POSITION  = 0.0    # Open: 0°
REVO3_CLOSE_POSITION = 80.0   # Default close for standard flex joints [0, 90°]
REVO3_THRESHOLD_RATIO = 0.90  # 90% threshold

# Per-joint safe close positions (hardware register spec):
#   Reg 240–260: min pos (X100), Reg 270–290: max pos (X100)
#   joint  0, 4, 8, 12 (side-swing) : [-15°, 15°]  → test at 12°
#   joint  1-3, 5-7, 9-11, 13-15, 17-18 (flex) : [0°, 90°] → test at 80°
#   joint 16 (thumb root)   : [0°,  50°] → test at 40°
#   joint 19 (thumb diff-1) : [0°, 105°] → test at 90°
#   joint 20 (thumb diff-2) : [0°, 120°] → test at 100°
REVO3_JOINT_CLOSE_POSITIONS: dict = {
    # Side-swing joints (±15°)
    0: 12.0, 4: 12.0, 8: 12.0, 12: 12.0,
    # Standard flex joints [0, 90°]
    1: 80.0, 2: 80.0, 3: 80.0,
    5: 80.0, 6: 80.0, 7: 80.0,
    9: 80.0, 10: 80.0, 11: 80.0,
    13: 80.0, 14: 80.0, 15: 80.0,
    17: 80.0, 18: 80.0,
    # Thumb special joints
    16: 40.0,    # [0, 50°]  — thumb root
    19: 90.0,    # [0, 105°] — thumb diff-1
    20: 100.0,   # [0, 120°] — thumb diff-2
}


def get_v3_joint_close_position(joint_id: int) -> float:
    """Return the safe test close position (degrees) for a given REVO3 joint."""
    return REVO3_JOINT_CLOSE_POSITIONS.get(joint_id, REVO3_CLOSE_POSITION)


# ── Speed test targets ────────────────────────────────────────────────────────
# Reg 300–320: min speed (X100), Reg 321–341: max speed (X100)
# Default range: 0–110 rpm (unidirectional)
REVO3_SPEED_TARGET    = 80.0   # Forward test target (rpm)
REVO3_SPEED_OPEN      = 0.0    # Stop / reset (rpm). Min=0 per hardware spec.
REVO3_SPEED_THRESHOLD = 0.80   # Accept if ≥80% of target

# ── Current test targets ──────────────────────────────────────────────────────
# Reg 200: global protect current (mA).  Reg 201–221: per-joint protect current.
# Defaults unknown; use conservative ±300 mA. Adjust via revo3_set_joint_protect_current.
REVO3_CURRENT_TARGET    = 300.0   # Forward target (mA)
REVO3_CURRENT_OPEN      = -300.0  # Reverse target (mA)
REVO3_CURRENT_THRESHOLD = 0.80    # Accept if ≥80% of target

# ── Colors ────────────────────────────────────────────────────────────────────
def _generate_v3_motor_colors():
    """Generate per-motor colors (21 total), grouped by finger."""
    finger_base_colors = {
        "Thumb":  (255, 107, 107),
        "Index":  ( 78, 205, 196),
        "Middle": ( 69, 183, 209),
        "Ring":   (255, 160, 122),
        "Pinky":  (152, 216, 200),
    }
    colors = [(128, 128, 128)] * REVO3_MOTOR_COUNT
    finger_motor_map = {
        "Thumb":  [18, 17, 16, 19, 20],
        "Index":  [15, 14, 13, 12],
        "Middle": [11, 10,  9,  8],
        "Ring":   [ 7,  6,  5,  4],
        "Pinky":  [ 3,  2,  1,  0],
    }
    for fname, motor_ids in finger_motor_map.items():
        base = finger_base_colors[fname]
        n = len(motor_ids)
        for j, mid in enumerate(motor_ids):
            factor = 1.0 - 0.15 * (j / max(n - 1, 1))
            colors[mid] = (int(base[0] * factor),
                           int(base[1] * factor),
                           int(base[2] * factor))
    return colors


REVO3_MOTOR_COLORS = _generate_v3_motor_colors()

REVO3_FINGER_COLORS = [
    (255, 107, 107),   # Thumb  — Red
    ( 78, 205, 196),   # Index  — Teal
    ( 69, 183, 209),   # Middle — Blue
    (255, 160, 122),   # Ring   — Orange
    (152, 216, 200),   # Pinky  — Green
]


# ── Worker ────────────────────────────────────────────────────────────────────

class TimingTestRevo3Worker(QObject):
    """Worker thread for Revo3 (21 joints) timing tests.

    Supports three view/control modes:
      Position — v3_set_motor_position, tracks position feedback
      Speed    — v3_set_motor_velocity, tracks velocity feedback
      Current  — v3_set_motor_current,  tracks current feedback

    Uses SharedDataManager for all motor feedback (no direct polling).
    Sends control commands at ~200 Hz during measurement for proper tracking.
    """

    log_message  = Signal(str)
    data_point   = Signal(list, list, list)   # actual: (positions, velocities, currents)
    ref_point    = Signal(list, list, list)   # setpoint: (ref_pos, ref_vel, ref_cur)
    stats_update = Signal(int, float)          # (total_read_count, elapsed_since_start)
    finished     = Signal()

    def __init__(self, device, slave_id, num_cycles, timeout,
                 test_mode, finger_index, shared_data,
                 view_mode="Position", signal_type="Step",
                 mit_kp: float = 5.0, mit_kd: float = 0.5):
        super().__init__()
        self.device        = device
        self.slave_id      = slave_id
        self.num_cycles    = num_cycles
        self.timeout       = timeout
        self.test_mode     = test_mode
        self.finger_index  = finger_index
        self.shared_data   = shared_data
        self.view_mode     = view_mode      # "Position" | "Speed" | "Current" | "MIT"
        self.signal_type   = signal_type    # "Step" | "Sine"
        self.mit_kp        = mit_kp
        self.mit_kd        = mit_kd
        self.is_running    = True
        self._total_read_count = 0
        self._test_start_time  = None

    def stop(self):
        self.is_running = False

    def _build_ref(self, joint_ids: list, mode: str, val_or_targets) -> tuple:
        """Build (ref_pos, ref_vel, ref_cur) arrays, size REVO3_MOTOR_COUNT.

        val_or_targets: float for uniform target, or dict {jid: float} for per-joint.
        """
        z = [0.0] * REVO3_MOTOR_COUNT
        ref_p, ref_v, ref_c = list(z), list(z), list(z)
        for jid in joint_ids:
            v = (val_or_targets.get(jid, 0.0)
                 if isinstance(val_or_targets, dict)
                 else val_or_targets)
            if mode == "Speed":
                ref_v[jid] = v
            elif mode == "Current":
                ref_c[jid] = v
            else:
                ref_p[jid] = v
        return ref_p, ref_v, ref_c

    # ── Low-level control ─────────────────────────────────────────────────────

    async def _v3_set_all_positions(self, positions):
        """Set all REVO3 motor positions (21 values, float degrees)."""
        await self.device.v3_set_all_motor_positions(self.slave_id, positions)

    async def _v3_set_all_velocities(self, velocities):
        """Set all REVO3 motor velocities (21 values, rpm)."""
        await self.device.v3_set_all_motor_velocities(self.slave_id, velocities)

    async def _v3_set_all_currents(self, currents):
        """Set all REVO3 motor currents (21 values, mA)."""
        await self.device.v3_set_all_motor_currents(self.slave_id, currents)

    async def _v3_set_joints_position(self, joint_ids: list, target_deg: float):
        """Set a subset of joints to the same target position (per-joint API)."""
        for jid in joint_ids:
            await self.device.v3_set_motor_position(self.slave_id, jid, target_deg)

    async def _v3_set_joints_velocity(self, joint_ids: list, target_vel: float):
        """Set a subset of joints to the same target velocity (rpm, per-joint API)."""
        for jid in joint_ids:
            await self.device.v3_set_motor_velocity(self.slave_id, jid, target_vel)

    async def _v3_set_joints_current(self, joint_ids: list, target_cur: float):
        """Set a subset of joints to the same target current (mA, per-joint API)."""
        for jid in joint_ids:
            await self.device.v3_set_motor_current(self.slave_id, jid, target_cur)

    # ── Feedback ──────────────────────────────────────────────────────────────

    def _v3_get_motor_data(self):
        """Return (positions, velocities, currents) lists from SharedDataManager."""
        zero = [0.0] * REVO3_MOTOR_COUNT
        if not self.shared_data:
            return zero, zero, zero
        v3_motor = self.shared_data.get_latest_v3_motor()
        if v3_motor:
            self._total_read_count += 1
            pos = list(v3_motor.positions)  if hasattr(v3_motor, 'positions')  and v3_motor.positions  else list(zero)
            vel = list(v3_motor.velocities) if hasattr(v3_motor, 'velocities') and v3_motor.velocities else list(zero)
            cur = list(v3_motor.currents)   if hasattr(v3_motor, 'currents')   and v3_motor.currents   else list(zero)
            return pos, vel, cur
        return list(zero), list(zero), list(zero)

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        """Run the REVO3 timing test (called from worker thread)."""
        self._test_start_time  = time.time()
        self._total_read_count = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if self.test_mode == MODE_ALL_FINGERS:
                loop.run_until_complete(self._run_all_fingers_test())
            else:
                loop.run_until_complete(self._run_single_finger_test())
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log_message.emit(f"Test error: {e}")
        finally:
            loop.close()
            self.finished.emit()

    # ── All-fingers test ──────────────────────────────────────────────────────

    async def _run_all_fingers_test(self):
        """Run all-fingers timing test (21 joints)."""
        mode = self.view_mode
        # Use REVO3_MOTOR_COUNT (21)
        n = REVO3_MOTOR_COUNT
        self.log_message.emit(f"=== Revo3 All Fingers Test ({mode} mode, {n} joints) ===")

        if mode == "Speed":
            target_fwd = [REVO3_SPEED_TARGET] * n
            target_rev = [REVO3_SPEED_OPEN]   * n
            init_cmd   = lambda: self._v3_set_all_velocities([0.0] * REVO3_MOTOR_COUNT)
            label_fwd  = f"FORWARD: 0 → {REVO3_SPEED_TARGET} rpm"
            label_rev  = f"REVERSE: {REVO3_SPEED_TARGET} → {REVO3_SPEED_OPEN} rpm"
        elif mode == "Current":
            target_fwd = [REVO3_CURRENT_TARGET] * n
            target_rev = [REVO3_CURRENT_OPEN]   * n
            init_cmd   = lambda: self._v3_set_all_currents([0.0] * REVO3_MOTOR_COUNT)
            label_fwd  = f"FORWARD: 0 → {REVO3_CURRENT_TARGET} mA"
            label_rev  = f"REVERSE: {REVO3_CURRENT_TARGET} → {REVO3_CURRENT_OPEN} mA"
        else:  # Position — per-joint safe targets (21 joints only)
            target_fwd = [get_v3_joint_close_position(jid) for jid in range(n)]
            target_rev = [REVO3_OPEN_POSITION] * n
            init_cmd   = lambda: self._v3_set_all_positions(
                [REVO3_OPEN_POSITION] * REVO3_MOTOR_COUNT)
            label_fwd  = "CLOSE: all joints → per-joint close target"
            label_rev  = "OPEN: all joints → 0°"

        self.log_message.emit("Moving to initial state...")
        await init_cmd()
        await asyncio.sleep(2.0)

        if self.signal_type == "Sine":
            await self._run_sine_loop(list(range(n)), mode)
            self.log_message.emit("\nSine wave tracking completed.")
            return

        close_times, open_times = [], []
        for cycle in range(self.num_cycles):
            if not self.is_running:
                break
            self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")

            self.log_message.emit(label_fwd)
            t = await self._measure_all_fingers(target_fwd, mode)
            close_times.append(t)
            self.log_message.emit(f"  Forward time: {t:.3f}s")

            self.log_message.emit(label_rev)
            t = await self._measure_all_fingers(target_rev, mode)
            open_times.append(t)
            self.log_message.emit(f"  Reverse time: {t:.3f}s")

        self._show_results("Revo3 All Fingers", close_times, open_times)

    # ── Single finger / joint test ────────────────────────────────────────────

    async def _run_single_finger_test(self):
        """Run single finger or single joint timing test.

        finger_index can be:
          - Finger name ("Index", "Thumb", ...)  → multiple joints
          - "M<n>"                               → single joint n
        """
        mode        = self.view_mode
        finger_name = self.finger_index
        if finger_name.startswith("M") and finger_name[1:].isdigit():
            joint_ids = [int(finger_name[1:])]
        else:
            joint_ids = REVO3_FINGER_JOINTS.get(finger_name, [])

        self.log_message.emit(
            f"=== Revo3 Single Test: {finger_name} ({mode} mode, joints={joint_ids}) ===")

        if self.signal_type == "Sine":
            self.log_message.emit("Moving to initial state (0)...")
            if mode == "Speed":
                await self._v3_set_joints_velocity(joint_ids, 0.0)
            elif mode == "Current":
                await self._v3_set_joints_current(joint_ids, 0.0)
            elif mode == "MIT":
                for jid in joint_ids:
                    await self.device.v3_set_motor_mit(
                        self.slave_id, jid, 0.0, 0.0, 0.0, self.mit_kp, self.mit_kd)
            else:
                for jid in joint_ids:
                    await self.device.v3_set_motor_position(self.slave_id, jid, 0.0)
            await asyncio.sleep(1.0)
            await self._run_sine_loop(joint_ids, mode, self.mit_kp, self.mit_kd)
            self.log_message.emit("\nSine wave tracking completed.")
            return

        close_times, open_times = [], []

        if mode == "Speed":
            self.log_message.emit("Moving to initial state (0 rpm)...")
            await self._v3_set_joints_velocity(joint_ids, 0.0)
            await asyncio.sleep(2.0)
            for cycle in range(self.num_cycles):
                if not self.is_running:
                    break
                self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")
                self.log_message.emit(f"FORWARD: 0 → {REVO3_SPEED_TARGET} rpm")
                t = await self._measure_single_finger(joint_ids, REVO3_SPEED_TARGET, mode)
                close_times.append(t)
                self.log_message.emit(f"  Forward time: {t:.3f}s")
                self.log_message.emit(f"REVERSE: {REVO3_SPEED_TARGET} → {REVO3_SPEED_OPEN} rpm")
                t = await self._measure_single_finger(joint_ids, REVO3_SPEED_OPEN, mode)
                open_times.append(t)
                self.log_message.emit(f"  Reverse time: {t:.3f}s")

        elif mode == "Current":
            self.log_message.emit("Moving to initial state (0 mA)...")
            await self._v3_set_joints_current(joint_ids, 0.0)
            await asyncio.sleep(2.0)
            for cycle in range(self.num_cycles):
                if not self.is_running:
                    break
                self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")
                self.log_message.emit(f"FORWARD: 0 → {REVO3_CURRENT_TARGET} mA")
                t = await self._measure_single_finger(joint_ids, REVO3_CURRENT_TARGET, mode)
                close_times.append(t)
                self.log_message.emit(f"  Forward time: {t:.3f}s")
                self.log_message.emit(f"REVERSE: {REVO3_CURRENT_TARGET} → {REVO3_CURRENT_OPEN} mA")
                t = await self._measure_single_finger(joint_ids, REVO3_CURRENT_OPEN, mode)
                open_times.append(t)
                self.log_message.emit(f"  Reverse time: {t:.3f}s")

        elif mode == "MIT":   # Impedance / force-position hybrid
            kp = self.mit_kp
            kd = self.mit_kd
            close_targets = {jid: get_v3_joint_close_position(jid) for jid in joint_ids}
            open_targets  = {jid: REVO3_OPEN_POSITION for jid in joint_ids}
            first_id  = joint_ids[0] if joint_ids else 0
            close_deg = close_targets.get(first_id, REVO3_CLOSE_POSITION)
            self.log_message.emit(
                f"Moving to initial state (MIT 0°, kp={kp}, kd={kd})...")
            for jid in joint_ids:
                await self.device.v3_set_motor_mit(
                    self.slave_id, jid, 0.0, 0.0, 0.0, kp, kd)
            await asyncio.sleep(2.0)
            for cycle in range(self.num_cycles):
                if not self.is_running:
                    break
                self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")
                self.log_message.emit(
                    f"MIT CLOSE: joints → {close_deg:.0f}° (kp={kp}, kd={kd})")
                t = await self._measure_single_finger_mit(
                    joint_ids, close_targets, kp, kd)
                close_times.append(t)
                self.log_message.emit(f"  Close time: {t:.3f}s")
                self.log_message.emit("MIT OPEN: joints → 0°")
                t = await self._measure_single_finger_mit(
                    joint_ids, open_targets, kp, kd)
                open_times.append(t)
                self.log_message.emit(f"  Open time: {t:.3f}s")

        else:  # Position — per-joint safe targets
            close_targets = {jid: get_v3_joint_close_position(jid) for jid in joint_ids}
            open_targets  = {jid: REVO3_OPEN_POSITION for jid in joint_ids}
            first_id  = joint_ids[0] if joint_ids else 0
            close_deg = close_targets.get(first_id, REVO3_CLOSE_POSITION)
            self.log_message.emit("Moving to initial position (0°)...")
            for jid in joint_ids:
                await self.device.v3_set_motor_position(self.slave_id, jid, REVO3_OPEN_POSITION)
            await asyncio.sleep(2.0)
            for cycle in range(self.num_cycles):
                if not self.is_running:
                    break
                self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")
                self.log_message.emit(
                    f"CLOSE: per-joint (e.g. M{first_id}={close_deg:.0f}°)")
                t = await self._measure_single_finger_pos(joint_ids, close_targets)
                close_times.append(t)
                self.log_message.emit(f"  Close time: {t:.3f}s")
                self.log_message.emit("OPEN: all → 0°")
                t = await self._measure_single_finger_pos(joint_ids, open_targets)
                open_times.append(t)
                self.log_message.emit(f"  Open time: {t:.3f}s")

        self._show_results(f"Revo3 {finger_name}", close_times, open_times)

    # ── Sine Tracking Loop ────────────────────────────────────────────────────

    async def _run_sine_loop(self, joint_ids: list, mode: str,
                             kp: float = 5.0, kd: float = 0.5):
        """Run continuous sine wave tracking test.

        For MIT mode, generates p_des and v_des (analytic derivative) and sends
        as impedance commands, providing both position and velocity feedforward.
        """
        import math
        start_time = time.time()
        freq = 0.5  # 0.5 Hz → period = 2 s per cycle
        # Sine duration is driven by num_cycles.  timeout (per-cycle Step limit)
        # acts only as a safety ceiling if it is set larger than the cycle duration.
        cycle_duration = self.num_cycles * (1.0 / freq)
        if self.timeout > 0 and self.timeout > cycle_duration:
            total_duration = self.timeout   # honour an explicitly longer timeout
        else:
            total_duration = cycle_duration  # num_cycles × period always wins
        self.log_message.emit(
            f"Playing Sine Wave ({freq}Hz, {self.num_cycles} cycles = {total_duration:.1f}s)...")

        if mode in ("Position", "MIT"):
            close_targets = {jid: get_v3_joint_close_position(jid) for jid in joint_ids}

        # Track the latest reference command (updated at ctrl rate, emitted at chart rate)
        curr_ref_p = [0.0] * REVO3_MOTOR_COUNT
        curr_ref_v = [0.0] * REVO3_MOTOR_COUNT
        curr_ref_c = [0.0] * REVO3_MOTOR_COUNT

        last_ctrl_time  = 0.0
        last_emit_time  = 0.0
        last_stats_time = 0.0
        ctrl_interval   = 0.01   # 100 Hz

        while self.is_running:
            await asyncio.sleep(0.001)
            elapsed = time.time() - start_time
            if elapsed >= total_duration:
                break

            if elapsed - last_ctrl_time >= ctrl_interval:
                phase = 2 * math.pi * freq * elapsed

                if mode in ("Position", "MIT"):
                    for jid in joint_ids:
                        max_deg = close_targets.get(jid, REVO3_CLOSE_POSITION)
                        # p_des: smooth 0→max→0 profile
                        p_des = (max_deg / 2.0) * (1.0 - math.cos(phase))
                        # v_des: analytic derivative (deg/s → rpm)
                        v_des_dps = (max_deg / 2.0) * 2 * math.pi * freq * math.sin(phase)
                        v_des_rpm = v_des_dps / 6.0  # 1 rpm = 6 deg/s
                        curr_ref_p[jid] = p_des
                        curr_ref_v[jid] = v_des_rpm
                        if mode == "MIT":
                            await self.device.v3_set_motor_mit(
                                self.slave_id, jid, p_des, v_des_rpm, 0.0, kp, kd)
                        else:
                            await self.device.v3_set_motor_position(
                                self.slave_id, jid, p_des)

                elif mode == "Speed":
                    val = REVO3_SPEED_TARGET * math.sin(phase)
                    for jid in joint_ids:
                        curr_ref_v[jid] = val
                    await self._v3_set_joints_velocity(joint_ids, val)

                elif mode == "Current":
                    val = REVO3_CURRENT_TARGET * math.sin(phase)
                    for jid in joint_ids:
                        curr_ref_c[jid] = val
                    await self._v3_set_joints_current(joint_ids, val)

                last_ctrl_time = elapsed

            # Emit chart data at ~50 Hz
            if elapsed - last_emit_time >= 0.02:
                all_pos, all_vel, all_cur = self._v3_get_motor_data()
                self.data_point.emit(all_pos, all_vel, all_cur)
                self.ref_point.emit(list(curr_ref_p), list(curr_ref_v), list(curr_ref_c))
                last_emit_time = elapsed

            if elapsed - last_stats_time >= 0.1:
                test_elapsed = (time.time() - self._test_start_time
                               if self._test_start_time else elapsed)
                self.stats_update.emit(self._total_read_count, test_elapsed)
                last_stats_time = elapsed

    # ── MIT measurement helper ────────────────────────────────────────────────

    async def _measure_single_finger_mit(self, joint_ids: list, targets: dict,
                                         kp: float, kd: float) -> float:
        """Measure response time using MIT impedance control (per-joint targets).

        τ = kp*(p_des - p_act) + kd*(v_des - v_act) + t_ff
        v_des = 0 (step command), t_ff = 0.

        ref_point emits (p_des_array, zeros, zeros) so the Position chart shows
        the step reference alongside the actual position curve.
        """
        ref_p, ref_v, ref_c = self._build_ref(joint_ids, "Position", targets)

        start_time = time.time()
        for jid in joint_ids:
            await self.device.v3_set_motor_mit(
                self.slave_id, jid, targets.get(jid, 0.0), 0.0, 0.0, kp, kd)

        last_emit_time  = 0.0
        last_stats_time = 0.0
        last_ctrl_time  = 0.0
        ctrl_interval   = 0.005   # 200 Hz

        while self.is_running:
            await asyncio.sleep(0.001)
            elapsed = time.time() - start_time

            try:
                if elapsed - last_ctrl_time >= ctrl_interval:
                    for jid in joint_ids:
                        await self.device.v3_set_motor_mit(
                            self.slave_id, jid, targets.get(jid, 0.0), 0.0, 0.0, kp, kd)
                    last_ctrl_time = elapsed

                all_pos, all_vel, all_cur = self._v3_get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = (time.time() - self._test_start_time
                                   if self._test_start_time else elapsed)
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                all_reached = True
                for jid in joint_ids:
                    target  = targets.get(jid, 0.0)
                    current = all_pos[jid]
                    if abs(target) < 1.0:
                        if abs(current - target) > 5.0:
                            all_reached = False
                            break
                    else:
                        if abs(current) < abs(target) * REVO3_THRESHOLD_RATIO:
                            all_reached = False
                            break

                if all_reached:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time

    # ── Results ───────────────────────────────────────────────────────────────

    def _show_results(self, name, close_times, open_times):
        if close_times and open_times:
            self.log_message.emit(f"\n{'=' * 50}")
            self.log_message.emit(f"{name} Timing Test Results")
            self.log_message.emit(f"{'=' * 50}")
            self.log_message.emit(f"Cycles: {len(close_times)}")
            self.log_message.emit(f"\nCLOSE/FORWARD:")
            self.log_message.emit(
                f"  Average: {sum(close_times)/len(close_times):.3f}s")
            self.log_message.emit(
                f"  Min: {min(close_times):.3f}s, Max: {max(close_times):.3f}s")
            self.log_message.emit(f"\nOPEN/REVERSE:")
            self.log_message.emit(
                f"  Average: {sum(open_times)/len(open_times):.3f}s")
            self.log_message.emit(
                f"  Min: {min(open_times):.3f}s, Max: {max(open_times):.3f}s")
            self.log_message.emit(f"{'=' * 50}")

    # ── Measurement helpers ───────────────────────────────────────────────────

    async def _measure_all_fingers(self, target_values: list, mode: str):
        """Measure all-fingers response time (REVO3, 21 joints)."""
        n = REVO3_MOTOR_COUNT
        padded_fwd = list(target_values) + [0.0] * (REVO3_MOTOR_COUNT - n)

        # Build constant reference arrays for this step
        ref_p = list(padded_fwd) if mode == "Position" else [0.0] * REVO3_MOTOR_COUNT
        ref_v = list(padded_fwd) if mode == "Speed"    else [0.0] * REVO3_MOTOR_COUNT
        ref_c = list(padded_fwd) if mode == "Current"  else [0.0] * REVO3_MOTOR_COUNT

        start_time = time.time()
        if mode == "Speed":
            await self._v3_set_all_velocities(padded_fwd)
            threshold_ratio = REVO3_SPEED_THRESHOLD
        elif mode == "Current":
            await self._v3_set_all_currents(padded_fwd)
            threshold_ratio = REVO3_CURRENT_THRESHOLD
        else:
            await self._v3_set_all_positions(padded_fwd)
            threshold_ratio = REVO3_THRESHOLD_RATIO

        last_emit_time  = 0.0
        last_stats_time = 0.0
        last_ctrl_time  = 0.0
        ctrl_interval   = 0.005   # 200 Hz

        while self.is_running:
            await asyncio.sleep(0.001)
            elapsed = time.time() - start_time

            try:
                if elapsed - last_ctrl_time >= ctrl_interval:
                    if mode == "Speed":
                        await self._v3_set_all_velocities(padded_fwd)
                    elif mode == "Current":
                        await self._v3_set_all_currents(padded_fwd)
                    else:
                        await self._v3_set_all_positions(padded_fwd)
                    last_ctrl_time = elapsed

                all_pos, all_vel, all_cur = self._v3_get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = (time.time() - self._test_start_time
                                   if self._test_start_time else elapsed)
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                feedback = all_vel if mode == "Speed" else \
                           all_cur if mode == "Current" else all_pos

                all_reached = True
                for jid in range(n):
                    target  = target_values[jid]
                    current = feedback[jid]
                    if abs(target) < 0.1:
                        if abs(current) > 5.0:
                            all_reached = False
                            break
                    else:
                        if abs(current) < abs(target) * threshold_ratio:
                            all_reached = False
                            break

                if all_reached:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time

    async def _measure_single_finger(self, joint_ids: list, target: float, mode: str):
        """Measure single finger/joint response time — uniform float target."""
        ref_p, ref_v, ref_c = self._build_ref(joint_ids, mode, target)

        start_time = time.time()
        if mode == "Speed":
            await self._v3_set_joints_velocity(joint_ids, target)
            threshold_ratio = REVO3_SPEED_THRESHOLD
        elif mode == "Current":
            await self._v3_set_joints_current(joint_ids, target)
            threshold_ratio = REVO3_CURRENT_THRESHOLD
        else:
            await self._v3_set_joints_position(joint_ids, target)
            threshold_ratio = REVO3_THRESHOLD_RATIO

        last_emit_time  = 0.0
        last_stats_time = 0.0
        last_ctrl_time  = 0.0
        ctrl_interval   = 0.005  # 200 Hz

        while self.is_running:
            await asyncio.sleep(0.001)
            elapsed = time.time() - start_time

            try:
                if elapsed - last_ctrl_time >= ctrl_interval:
                    if mode == "Speed":
                        await self._v3_set_joints_velocity(joint_ids, target)
                    elif mode == "Current":
                        await self._v3_set_joints_current(joint_ids, target)
                    else:
                        await self._v3_set_joints_position(joint_ids, target)
                    last_ctrl_time = elapsed

                all_pos, all_vel, all_cur = self._v3_get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = (time.time() - self._test_start_time
                                   if self._test_start_time else elapsed)
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                feedback = all_vel if mode == "Speed" else \
                           all_cur if mode == "Current" else all_pos

                all_reached = True
                for jid in joint_ids:
                    current = feedback[jid]
                    if abs(target) < 0.1:
                        if abs(current) > 5.0:
                            all_reached = False
                            break
                    else:
                        if abs(current) < abs(target) * threshold_ratio:
                            all_reached = False
                            break

                if all_reached:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time

    async def _measure_single_finger_pos(self, joint_ids: list, targets: dict):
        """Measure single finger/joint position response time — per-joint targets."""
        ref_p, ref_v, ref_c = self._build_ref(joint_ids, "Position", targets)

        start_time = time.time()
        for jid in joint_ids:
            await self.device.v3_set_motor_position(
                self.slave_id, jid, targets.get(jid, 0.0))

        last_emit_time  = 0.0
        last_stats_time = 0.0
        last_ctrl_time  = 0.0
        ctrl_interval   = 0.005   # 200 Hz

        while self.is_running:
            await asyncio.sleep(0.001)
            elapsed = time.time() - start_time
            try:
                if elapsed - last_ctrl_time >= ctrl_interval:
                    for jid in joint_ids:
                        await self.device.v3_set_motor_position(
                            self.slave_id, jid, targets.get(jid, 0.0))
                    last_ctrl_time = elapsed

                all_pos, all_vel, all_cur = self._v3_get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = (time.time() - self._test_start_time
                                   if self._test_start_time else elapsed)
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                all_reached = True
                for jid in joint_ids:
                    target  = targets.get(jid, 0.0)
                    current = all_pos[jid]
                    if abs(target) < 1.0:
                        if abs(current - target) > 5.0:
                            all_reached = False
                            break
                    else:
                        if abs(current) < abs(target) * REVO3_THRESHOLD_RATIO:
                            all_reached = False
                            break

                if all_reached:
                    self.data_point.emit(all_pos, all_vel, all_cur)
                    self.ref_point.emit(ref_p, ref_v, ref_c)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time
