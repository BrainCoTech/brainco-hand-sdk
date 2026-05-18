"""V1/V2 Timing Test Worker

Handles Revo1/Revo2 (6-DOF, motor values 0-1000) timing tests.
"""

import asyncio
import time
import sys
import os
from typing import TYPE_CHECKING
from PySide6.QtCore import QObject, Signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import sdk, logger, libstark, is_protobuf_device, supports_durations_api

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

from .constants import MOTOR_NAMES_EN, MOTOR_COUNT

# ── Test mode constants (shared with panel) ──────────────────────────────────
MODE_ALL_FINGERS  = 0
MODE_SINGLE_FINGER = 1

# Single finger options for V1/V2 (Index/Middle/Ring/Pinky, motor indices 2-5)
SINGLE_FINGER_OPTIONS = [
    ('Index',  2),
    ('Middle', 3),
    ('Ring',   4),
    ('Pinky',  5),
]

# V1/V2 position thresholds
THRESHOLD_CLOSE = 900   # "close enough" for a closing move (90% of 1000)
THRESHOLD_OPEN  = 100   # "close enough" for an opening move


class TimingTestRevo2Worker(QObject):
    """Worker thread for V1/V2 (Revo1/Revo2) timing tests.

    Uses SharedDataManager for motor status.
    Separates measurement frequency from UI update frequency:
      - data_point   : throttled to ~50 Hz for chart rendering
      - stats_update : reports actual read count / frequency at ~10 Hz
    """

    log_message  = Signal(str)
    data_point   = Signal(list, list, list)   # (positions, speeds, currents)
    stats_update = Signal(int, float)          # (total_read_count, elapsed_since_start)
    finished     = Signal()

    def __init__(self, device, slave_id, num_cycles, timeout,
                 test_mode, finger_index, shared_data, view_mode="Position", signal_type="Step"):
        super().__init__()
        self.device       = device
        self.slave_id     = slave_id
        self.num_cycles   = num_cycles
        self.timeout      = timeout
        self.test_mode    = test_mode
        self.finger_index = finger_index   # motor index for single-finger mode
        self.shared_data  = shared_data
        self.view_mode    = view_mode      # V1/V2 only uses "Position"
        self.is_running   = True
        self._total_read_count = 0
        self._test_start_time  = None

    @property
    def hw_type(self):
        return self.shared_data.hw_type if self.shared_data else None

    def stop(self):
        self.is_running = False

    # ── Low-level helpers ────────────────────────────────────────────────────

    async def _set_positions(self, positions, durations=None):
        """Send position commands to V1/V2 device."""
        if durations is None:
            durations = [1] * len(positions)
        if supports_durations_api and supports_durations_api(self.device):
            await self.device.set_finger_positions_with_durations(
                self.slave_id, positions, durations)
        else:
            await self.device.set_finger_positions(self.slave_id, positions)

    def _get_motor_data(self):
        """Return (positions, speeds, currents) from SharedDataManager."""
        if not self.shared_data:
            return [0] * MOTOR_COUNT, [0] * MOTOR_COUNT, [0] * MOTOR_COUNT
        motor = self.shared_data.get_latest_motor()
        if motor:
            self._total_read_count += 1
            positions = list(motor.positions) if hasattr(motor, 'positions') and motor.positions \
                else [0] * MOTOR_COUNT
            speeds    = list(motor.speeds)    if hasattr(motor, 'speeds')    and motor.speeds    \
                else [0] * MOTOR_COUNT
            currents  = list(motor.currents)  if hasattr(motor, 'currents')  and motor.currents  \
                else [0] * MOTOR_COUNT
            return positions, speeds, currents
        return [0] * MOTOR_COUNT, [0] * MOTOR_COUNT, [0] * MOTOR_COUNT

    def _get_positions(self):
        positions, _, _ = self._get_motor_data()
        return positions

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self):
        """Run the V1/V2 timing test (called from worker thread)."""
        self._test_start_time = time.time()
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

    # ── V1/V2 tests ──────────────────────────────────────────────────────────

    async def _run_all_fingers_test(self):
        """Run all-fingers timing test (V1/V2)."""
        self.log_message.emit("=== All Fingers Timing Test ===")

        open_positions  = [0, 0, 0, 0, 0, 0]
        close_positions = [1000, 1000, 1000, 1000, 1000, 1000]
        durations = [1] * 6

        self.log_message.emit("Moving to initial position...")
        await self._set_positions(open_positions, durations)
        await asyncio.sleep(2.0)

        close_times, open_times = [], []

        for cycle in range(self.num_cycles):
            if not self.is_running:
                break
            self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")

            self.log_message.emit("CLOSE: 0% → 100%")
            close_time = await self._measure_all_fingers_movement(close_positions, durations)
            close_times.append(close_time)
            self.log_message.emit(f"  Close time: {close_time:.3f}s")

            self.log_message.emit("OPEN: 100% → 0%")
            open_time = await self._measure_all_fingers_movement(open_positions, durations)
            open_times.append(open_time)
            self.log_message.emit(f"  Open time: {open_time:.3f}s")

        self._show_results("All Fingers", close_times, open_times)

    async def _run_single_finger_test(self):
        """Run single-finger timing test (V1/V2)."""
        finger_name = MOTOR_NAMES_EN[self.finger_index]
        self.log_message.emit(f"=== Single Finger Test: {finger_name} ===")

        open_positions  = [0, 0, 0, 0, 0, 0]
        close_positions = [0, 0, 0, 0, 0, 0]
        close_positions[self.finger_index] = 1000
        durations = [1] * 6

        self.log_message.emit("Moving to initial position...")
        await self._set_positions(open_positions, durations)
        await asyncio.sleep(2.0)

        close_times, open_times = [], []

        for cycle in range(self.num_cycles):
            if not self.is_running:
                break
            self.log_message.emit(f"\n--- Cycle {cycle + 1}/{self.num_cycles} ---")

            self.log_message.emit(f"CLOSE: {finger_name} 0% → 100%")
            close_time = await self._measure_single_finger_movement(
                close_positions, durations, self.finger_index)
            close_times.append(close_time)
            self.log_message.emit(f"  Close time: {close_time:.3f}s")

            self.log_message.emit(f"OPEN: {finger_name} 100% → 0%")
            open_time = await self._measure_single_finger_movement(
                open_positions, durations, self.finger_index)
            open_times.append(open_time)
            self.log_message.emit(f"  Open time: {open_time:.3f}s")

        self._show_results(finger_name, close_times, open_times)

    # ── Results ──────────────────────────────────────────────────────────────

    def _show_results(self, name, close_times, open_times):
        if close_times and open_times:
            self.log_message.emit(f"\n{'=' * 50}")
            self.log_message.emit(f"{name} Timing Test Results")
            self.log_message.emit(f"{'=' * 50}")
            self.log_message.emit(f"Cycles: {len(close_times)}")
            self.log_message.emit(f"\nCLOSE:")
            self.log_message.emit(f"  Average: {sum(close_times)/len(close_times):.3f}s")
            self.log_message.emit(f"  Min: {min(close_times):.3f}s, Max: {max(close_times):.3f}s")
            self.log_message.emit(f"\nOPEN:")
            self.log_message.emit(f"  Average: {sum(open_times)/len(open_times):.3f}s")
            self.log_message.emit(f"  Min: {min(open_times):.3f}s, Max: {max(open_times):.3f}s")
            self.log_message.emit(f"{'=' * 50}")

    # ── Measurement helpers ──────────────────────────────────────────────────

    async def _measure_all_fingers_movement(self, target_positions, durations):
        """Measure all-fingers movement time (V1/V2)."""
        start_time = time.time()
        await self._set_positions(target_positions, durations)
        last_emit_time  = 0.0
        last_stats_time = 0.0

        while self.is_running:
            await asyncio.sleep(0.01)
            elapsed = time.time() - start_time

            try:
                positions, speeds, currents = self._get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(positions, speeds, currents)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = time.time() - self._test_start_time \
                        if self._test_start_time else elapsed
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                all_reached = True
                for i in range(MOTOR_COUNT):
                    target = target_positions[i]
                    current = positions[i]
                    if target >= 900:
                        if current < THRESHOLD_CLOSE:
                            all_reached = False
                            break
                    else:
                        if current > THRESHOLD_OPEN:
                            all_reached = False
                            break

                if all_reached:
                    self.data_point.emit(positions, speeds, currents)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time

    async def _measure_single_finger_movement(self, target_positions, durations, finger_idx):
        """Measure single-finger movement time (V1/V2)."""
        start_time = time.time()
        await self._set_positions(target_positions, durations)
        last_emit_time  = 0.0
        last_stats_time = 0.0

        while self.is_running:
            await asyncio.sleep(0.01)
            elapsed = time.time() - start_time

            try:
                positions, speeds, currents = self._get_motor_data()

                if elapsed - last_emit_time >= 0.02:
                    self.data_point.emit(positions, speeds, currents)
                    last_emit_time = elapsed

                if elapsed - last_stats_time >= 0.1:
                    test_elapsed = time.time() - self._test_start_time \
                        if self._test_start_time else elapsed
                    self.stats_update.emit(self._total_read_count, test_elapsed)
                    last_stats_time = elapsed

                target  = target_positions[finger_idx]
                current = positions[finger_idx]
                if target >= 900:
                    reached = current >= THRESHOLD_CLOSE
                else:
                    reached = current <= THRESHOLD_OPEN

                if reached:
                    self.data_point.emit(positions, speeds, currents)
                    return elapsed
            except Exception:
                pass

            if elapsed >= self.timeout:
                return elapsed

        return time.time() - start_time
