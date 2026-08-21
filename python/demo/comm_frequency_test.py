#!/usr/bin/env python3
"""
Communication Frequency Test - Python Version

Tests communication frequency and performance with auto-detection support.
Supports: Modbus (RS485), CAN 2.0, CANFD, SocketCAN

Run:
    python comm_frequency_test.py              # Auto-detect, interactive menu
    python comm_frequency_test.py 1            # Run specific test (1-4)
    python comm_frequency_test.py 0            # Run all tests
    python comm_frequency_test.py 1 --duration 10 --target-hz 100 --output report.json
    python comm_frequency_test.py 2 --write-target-hz 50 --yes
    python comm_frequency_test.py -h           # Show help

Test modes:
    1. get_motor_status read frequency
    2. set_finger_positions write frequency
    3. Mixed function frequency (read + control)
    4. Long-term stability test

Write, mixed, and all-tests modes move the fingers and require confirmation unless
--yes is supplied. They restore the captured initial finger positions after the
test. Read-only mode is safe to run without motion confirmation.

The benchmark automatically initializes the first detected CANFD, CAN 2.0,
SocketCAN, or Modbus device. No protocol-specific setup is required.
"""

import asyncio
import json
import sys
import os
import time
import statistics
import platform
from collections import Counter
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import List, Optional, Dict, Any

# Setup path and imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import sdk, check_sdk, get_hw_type_name, get_protocol_display_name, logger, baudrate_to_int

check_sdk()


@dataclass
class TestConfig:
    """Test configuration"""
    test_duration: float = 5.0       # Single test duration (seconds)
    max_test_count: int = 10000      # Maximum test count
    target_frequency: float = 1000.0 # Read/mixed target frequency (Hz); 0 means maximum throughput
    write_target_frequency: float = 50.0
    stability_frequency: float = 100.0
    warmup_duration: float = 1.0
    stability_duration: float = 60.0
    sample_interval: float = 1.0     # Sample interval (seconds)
    progress_every: int = 0          # Disable measured-loop logging by default


@dataclass
class TestResult:
    """Single test result"""
    success: bool
    elapsed_ms: float
    timestamp: float
    operation: str
    error_msg: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class ConnectionInfo:
    """Connection info for test report"""
    adapter_type: str
    protocol: str
    port_name: str
    slave_id: int
    baudrate: int
    data_baudrate: int = 0

    def print_header(self):
        print(f"Connection:       {self.protocol} via {self.adapter_type}")
        print(f"Port:             {self.port_name}")
        print(f"Slave ID:         0x{self.slave_id:02X} ({self.slave_id})")
        # Convert baudrate to actual bps value
        # Note: Baudrate enum's int() returns index (0-6), not bps value
        baud = baudrate_to_int(self.baudrate) if hasattr(self.baudrate, 'int_value') else self.baudrate
        try:
            data_baud = int(self.data_baudrate)
        except (TypeError, ValueError):
            data_baud = 0
        if data_baud > 0:
            print(f"Baudrate:         {baud / 1_000_000:.0f} Mbps / {data_baud / 1_000_000:.0f} Mbps")
        elif baud >= 1_000_000:
            print(f"Baudrate:         {baud / 1_000_000:.0f} Mbps")
        elif baud > 0:
            print(f"Baudrate:         {baud} bps")
        else:
            print(f"Baudrate:         N/A")


@dataclass
class FrequencyTestReport:
    """Frequency test report"""
    function_name: str
    connection: ConnectionInfo
    total_tests: int
    successful_tests: int
    failed_tests: int
    success_rate: float
    avg_latency_ms: float
    max_latency_ms: float
    min_latency_ms: float
    std_dev_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    attempt_frequency_hz: float
    actual_frequency_hz: float
    target_frequency_hz: float
    total_duration_secs: float
    error_types: Dict[str, int]
    operation_stats: Dict[str, Dict[str, Any]]

    def print_report(self):
        print(f"\n{'=' * 60}")
        print(f"📊 {self.function_name} frequency test report")
        print("=" * 60)
        print(f"System:           {platform.system()} {platform.release()}")
        print(f"Language:         Python {platform.python_version()}")
        self.connection.print_header()
        print()
        print(f"Total tests:      {self.total_tests}")
        print(f"Successful tests: {self.successful_tests}")
        print(f"Failed tests:     {self.failed_tests}")
        print(f"Success rate:     {self.success_rate:.1f}%")
        print()
        print(f"Average latency:  {self.avg_latency_ms:.2f} ms")
        print(f"Minimum latency:  {self.min_latency_ms:.2f} ms")
        print(f"Maximum latency:  {self.max_latency_ms:.2f} ms")
        print(f"Std deviation:    {self.std_dev_ms:.2f} ms")
        print(f"P50/P95/P99:      {self.p50_latency_ms:.2f} / {self.p95_latency_ms:.2f} / {self.p99_latency_ms:.2f} ms")
        print()
        print(f"Attempt rate:     {self.attempt_frequency_hz:.1f} Hz")
        print(f"Successful rate:  {self.actual_frequency_hz:.1f} Hz")
        print(f"Target frequency: {self.target_frequency_hz:.1f} Hz")
        if self.target_frequency_hz > 0:
            print(f"Achievement rate: {self.actual_frequency_hz / self.target_frequency_hz * 100:.1f}%")
        else:
            print("Achievement rate: N/A (maximum-throughput mode)")
        print(f"Test duration:    {self.total_duration_secs:.1f} s")
        if self.error_types:
            print(f"Errors:           {self.error_types}")
        if len(self.operation_stats) > 1:
            print("Operation breakdown:")
            for operation, stats in sorted(self.operation_stats.items()):
                print(
                    f"  {operation:<8} count={int(stats['successful_count'])}, "
                    f"avg={stats['avg_latency_ms']:.2f}ms, p95={stats['p95_latency_ms']:.2f}ms"
                )


def percentile(values: List[float], percent: float) -> float:
    """Calculate an interpolated percentile without third-party dependencies."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percent / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def detect_adapter_type(port_name: str, protocol_type) -> str:
    """Detect adapter type from port name and protocol"""
    # SocketCAN interface
    if port_name.startswith("can") or port_name.startswith("vcan"):
        return "SocketCAN"
    
    # Check protocol type
    if protocol_type == sdk.StarkProtocolType.Modbus:
        return "USB-RS485"
    elif protocol_type in [sdk.StarkProtocolType.Can, sdk.StarkProtocolType.CanFd]:
        if "ttyUSB" in port_name or "ttyACM" in port_name or "COM" in port_name:
            return "ZQWL USB-CAN"
        return "CAN Adapter"
    return "Unknown"


class CommFrequencyTester:
    """Communication frequency tester"""

    def __init__(self, ctx, slave_id: int, connection_info: ConnectionInfo, config: TestConfig):
        self.ctx = ctx
        self.slave_id = slave_id
        self.connection_info = connection_info
        self.config = config

    async def _pace(self, next_deadline: float, target_frequency: float) -> float:
        """Pace calls against an absolute deadline to avoid cumulative sleep drift."""
        if target_frequency <= 0:
            return time.perf_counter()

        period = 1.0 / target_frequency
        next_deadline += period
        now = time.perf_counter()
        if next_deadline > now:
            await asyncio.sleep(next_deadline - now)
        elif now - next_deadline > period:
            # Do not issue a burst of catch-up requests after a long stall.
            next_deadline = now
        return next_deadline

    async def warm_up(self):
        """Warm up the connection with read-only requests excluded from results."""
        if self.config.warmup_duration <= 0:
            return

        print(f"\nWarming up connection ({self.config.warmup_duration:.1f}s, read-only)...")
        start_time = time.perf_counter()
        next_deadline = start_time
        while time.perf_counter() - start_time < self.config.warmup_duration:
            try:
                await self.ctx.get_motor_status(self.slave_id)
            except Exception:
                pass
            next_deadline = await self._pace(next_deadline, self.config.target_frequency)

    async def _capture_positions(self) -> Optional[List[int]]:
        """Capture the current hand position before a motion benchmark."""
        try:
            status = await self.ctx.get_motor_status(self.slave_id)
            positions = list(status.positions)
            return positions if len(positions) == 6 else None
        except Exception as exc:
            logger.error(f"Failed to capture initial positions: {exc}")
            return None

    async def _restore_positions(self, positions: Optional[List[int]]):
        """Best-effort restoration of the hand position after motion tests."""
        if positions is None:
            return
        try:
            await self.ctx.set_finger_positions(self.slave_id, positions)
            logger.info(f"Restored initial finger positions: {positions}")
        except Exception as exc:
            logger.error(f"Failed to restore initial positions: {exc}")

    async def test_get_motor_status_frequency(self) -> FrequencyTestReport:
        """Test 1: get_motor_status read frequency"""
        print("\n📊 Starting get_motor_status read frequency test...")

        results = []
        start_time = time.perf_counter()
        next_deadline = start_time
        test_count = 0

        while (time.perf_counter() - start_time) < self.config.test_duration and test_count < self.config.max_test_count:
            test_start = time.perf_counter()

            try:
                await self.ctx.get_motor_status(self.slave_id)
                elapsed_ms = (time.perf_counter() - test_start) * 1000
                results.append(TestResult(True, elapsed_ms, time.perf_counter() - start_time, "read"))
            except Exception as e:
                elapsed_ms = (time.perf_counter() - test_start) * 1000
                results.append(TestResult(False, elapsed_ms, time.perf_counter() - start_time, "read", str(e), type(e).__name__))

            if self.config.progress_every > 0 and (test_count + 1) % self.config.progress_every == 0:
                logger.info(f"  Test {test_count}, latency: {results[-1].elapsed_ms:.2f}ms")

            test_count += 1

            next_deadline = await self._pace(next_deadline, self.config.target_frequency)

        total_duration = time.perf_counter() - start_time
        return self._generate_report("get_motor_status", results, total_duration, self.config.target_frequency)


    async def test_set_finger_positions_frequency(self) -> FrequencyTestReport:
        """Test 2: set_finger_positions write frequency"""
        print("\n📊 Starting set_finger_positions write frequency test...")

        results = []
        start_time = time.perf_counter()
        next_deadline = start_time
        test_count = 0

        position_sequences = [
            [400, 400, 1000, 1000, 1000, 1000],
            [400, 400, 0, 0, 0, 0],
            [400, 400, 500, 500, 500, 500],
            [400, 400, 0, 0, 0, 0],
        ]

        while (time.perf_counter() - start_time) < self.config.test_duration and test_count < self.config.max_test_count:
            test_start = time.perf_counter()
            positions = position_sequences[test_count % len(position_sequences)]

            try:
                await self.ctx.set_finger_positions(self.slave_id, positions)
                elapsed_ms = (time.perf_counter() - test_start) * 1000
                results.append(TestResult(True, elapsed_ms, time.perf_counter() - start_time, "write"))
            except Exception as e:
                elapsed_ms = (time.perf_counter() - test_start) * 1000
                results.append(TestResult(False, elapsed_ms, time.perf_counter() - start_time, "write", str(e), type(e).__name__))

            if self.config.progress_every > 0 and (test_count + 1) % self.config.progress_every == 0:
                logger.info(f"  Test {test_count}, latency: {results[-1].elapsed_ms:.2f}ms")

            test_count += 1

            next_deadline = await self._pace(next_deadline, self.config.write_target_frequency)

        total_duration = time.perf_counter() - start_time
        return self._generate_report("set_finger_positions", results, total_duration, self.config.write_target_frequency)

    async def test_mixed_frequency(self) -> FrequencyTestReport:
        """Test 3: Mixed function frequency (read + control)"""
        print("\n📊 Starting mixed function frequency test...")

        results = []
        start_time = time.perf_counter()
        next_deadline = start_time
        test_count = 0

        position_sequences = [
            [400, 400, 0, 0, 0, 0],
            [400, 400, 300, 300, 300, 300],
            [400, 400, 600, 600, 600, 600],
            [400, 400, 1000, 1000, 1000, 1000],
        ]

        while (time.perf_counter() - start_time) < self.config.test_duration and test_count < self.config.max_test_count:
            test_start = time.perf_counter()

            try:
                if test_count % 5 == 0:
                    operation = "write"
                    positions = position_sequences[(test_count // 5) % len(position_sequences)]
                    await self.ctx.set_finger_positions(self.slave_id, positions)
                else:
                    operation = "read"
                    await self.ctx.get_motor_status(self.slave_id)

                elapsed_ms = (time.perf_counter() - test_start) * 1000
                results.append(TestResult(True, elapsed_ms, time.perf_counter() - start_time, operation))
            except Exception as e:
                elapsed_ms = (time.perf_counter() - test_start) * 1000
                operation = "write" if test_count % 5 == 0 else "read"
                results.append(TestResult(False, elapsed_ms, time.perf_counter() - start_time, operation, str(e), type(e).__name__))

            if self.config.progress_every > 0 and (test_count + 1) % self.config.progress_every == 0:
                action = "position" if test_count % 5 == 0 else "status"
                logger.info(f"  Test {test_count}, latency: {results[-1].elapsed_ms:.2f}ms, action: {action}")

            test_count += 1
            next_deadline = await self._pace(next_deadline, self.config.target_frequency)

        total_duration = time.perf_counter() - start_time
        return self._generate_report("mixed_functions", results, total_duration, self.config.target_frequency)


    async def test_stability(self) -> Dict[str, Any]:
        """Test 4: Long-term stability test"""
        print(f"\n📊 Starting stability test ({self.config.stability_duration:.0f}s)...")

        stability_results = {
            'samples': [],
            'successful_samples': [],
            'avg_latencies': [],
            'error_rates': [],
            'timestamps': []
        }

        start_time = time.perf_counter()
        end_time = start_time + self.config.stability_duration
        next_deadline = start_time
        sample_count = 0

        while time.perf_counter() < end_time:
            sample_start = time.perf_counter()
            sample_end = min(sample_start + self.config.sample_interval, end_time)
            sample_results = []

            while time.perf_counter() < sample_end:
                test_start = time.perf_counter()

                try:
                    await self.ctx.get_motor_status(self.slave_id)
                    elapsed_ms = (time.perf_counter() - test_start) * 1000
                    sample_results.append((True, elapsed_ms))
                except Exception:
                    elapsed_ms = (time.perf_counter() - test_start) * 1000
                    sample_results.append((False, elapsed_ms))

                next_deadline = await self._pace(next_deadline, self.config.stability_frequency)

            successful = [e for s, e in sample_results if s]
            total_count = len(sample_results)
            success_count = len(successful)

            avg_latency = statistics.mean(successful) if successful else 0
            error_rate = (total_count - success_count) / total_count * 100 if total_count > 0 else 0

            stability_results['samples'].append(total_count)
            stability_results['successful_samples'].append(success_count)
            stability_results['avg_latencies'].append(avg_latency)
            stability_results['error_rates'].append(error_rate)
            stability_results['timestamps'].append(time.perf_counter() - start_time)

            sample_count += 1
            if sample_count % 5 == 0:
                logger.info(f"  Sample {sample_count}, latency: {avg_latency:.2f}ms, error rate: {error_rate:.1f}%")

        return stability_results

    def _generate_report(self, function_name: str, results: List[TestResult],
                         total_duration: float, target_frequency: float) -> FrequencyTestReport:
        """Generate test report"""
        successful = [r for r in results if r.success]
        total_tests = len(results)
        successful_tests = len(successful)
        failed_tests = total_tests - successful_tests
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0

        if successful:
            latencies = [r.elapsed_ms for r in successful]
            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0
        else:
            avg_latency = max_latency = min_latency = std_dev = 0

        attempt_frequency = total_tests / total_duration if total_duration > 0 else 0
        successful_frequency = successful_tests / total_duration if total_duration > 0 else 0
        error_types = dict(Counter(r.error_type or "UnknownError" for r in results if not r.success))
        operation_stats = {}
        for operation in sorted({r.operation for r in successful}):
            operation_latencies = [r.elapsed_ms for r in successful if r.operation == operation]
            operation_stats[operation] = {
                "successful_count": len(operation_latencies),
                "avg_latency_ms": statistics.mean(operation_latencies),
                "p95_latency_ms": percentile(operation_latencies, 95),
            }

        return FrequencyTestReport(
            function_name=function_name,
            connection=self.connection_info,
            total_tests=total_tests,
            successful_tests=successful_tests,
            failed_tests=failed_tests,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            max_latency_ms=max_latency,
            min_latency_ms=min_latency,
            std_dev_ms=std_dev,
            p50_latency_ms=percentile(latencies, 50) if successful else 0,
            p95_latency_ms=percentile(latencies, 95) if successful else 0,
            p99_latency_ms=percentile(latencies, 99) if successful else 0,
            attempt_frequency_hz=attempt_frequency,
            actual_frequency_hz=successful_frequency,
            target_frequency_hz=target_frequency,
            total_duration_secs=total_duration,
            error_types=error_types,
            operation_stats=operation_stats,
        )

    async def run_test(self, test_num: int):
        """Run specific test"""
        initial_positions = await self._capture_positions() if test_num in (2, 3) else None
        if test_num in (2, 3) and initial_positions is None:
            raise RuntimeError("Unable to capture initial positions; motion test aborted")
        try:
            if test_num == 1:
                report = await self.test_get_motor_status_frequency()
                report.print_report()
                return {"reports": [report], "stability": None}
            elif test_num == 2:
                report = await self.test_set_finger_positions_frequency()
                report.print_report()
                return {"reports": [report], "stability": None}
            elif test_num == 3:
                report = await self.test_mixed_frequency()
                report.print_report()
                return {"reports": [report], "stability": None}
            elif test_num == 4:
                stability = await self.test_stability()
                self._print_stability_results(stability)
                return {"reports": [], "stability": stability}
            else:
                print(f"Invalid test number: {test_num}")
                return {"reports": [], "stability": None}
        finally:
            await self._restore_positions(initial_positions)

    async def run_all_tests(self):
        """Run all tests"""
        reports = []

        report1 = await self.test_get_motor_status_frequency()
        report1.print_report()
        reports.append(report1)

        initial_positions = await self._capture_positions()
        if initial_positions is None:
            raise RuntimeError("Unable to capture initial positions; motion tests aborted")
        try:
            report2 = await self.test_set_finger_positions_frequency()
            report2.print_report()
            reports.append(report2)

            report3 = await self.test_mixed_frequency()
            report3.print_report()
            reports.append(report3)
        finally:
            await self._restore_positions(initial_positions)

        stability = await self.test_stability()
        self._print_stability_results(stability)

        print(f"\n{'=' * 60}")
        print("📊 Test Summary")
        print("=" * 60)
        for report in reports:
            print(f"{report.function_name}: {report.actual_frequency_hz:.1f} Hz ({report.success_rate:.1f}% success)")
        return {"reports": reports, "stability": stability}

    def _print_stability_results(self, stability: Dict[str, Any]):
        """Print stability test results"""
        print(f"\n{'=' * 60}")
        print("📊 Stability Test Results")
        print("=" * 60)
        self.connection_info.print_header()
        print()

        if stability['avg_latencies']:
            total_attempts = sum(stability['samples'])
            total_successes = sum(stability['successful_samples'])
            weighted_latency = sum(
                latency * count
                for latency, count in zip(stability['avg_latencies'], stability['successful_samples'])
            )
            overall_avg = weighted_latency / total_successes if total_successes else 0
            overall_error = (
                (total_attempts - total_successes) / total_attempts * 100
                if total_attempts else 0
            )
            max_error = max(stability['error_rates'])
            print(f"Average latency:    {overall_avg:.2f} ms")
            print(f"Average error rate: {overall_error:.2f}%")
            print(f"Maximum error rate: {max_error:.2f}%")
            print(f"Sample count:       {len(stability['samples'])}")
        else:
            print("No stability data collected")


def requires_motion_confirmation(test_num: int) -> bool:
    """Return whether a test sends finger position commands."""
    return test_num in (0, 2, 3)


def confirm_motion_test(test_num: int, assume_yes: bool) -> bool:
    """Require explicit consent before running tests that move the hand."""
    if not requires_motion_confirmation(test_num) or assume_yes:
        return True
    print("\nWARNING: This test sends position commands and will move the fingers.")
    answer = input("Ensure the hand can move safely, then type 'yes' to continue: ").strip().lower()
    return answer == "yes"


def save_results(output_path: str, config: TestConfig, result_data: Dict[str, Any]):
    """Save machine-readable benchmark results for later comparison."""
    reports = []
    for report in result_data.get("reports", []):
        report_data = {
            field.name: getattr(report, field.name)
            for field in fields(report)
            if field.name != "connection"
        }
        report_data["connection"] = {
            "adapter_type": report.connection.adapter_type,
            "protocol": report.connection.protocol,
            "port_name": report.connection.port_name,
            "slave_id": report.connection.slave_id,
            "baudrate": baudrate_to_int(report.connection.baudrate),
            "data_baudrate": int(report.connection.data_baudrate or 0),
        }
        reports.append(report_data)

    payload = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "config": asdict(config),
        "reports": reports,
        "stability": result_data.get("stability"),
    }
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved to: {path.resolve()}")


def show_menu() -> Optional[int]:
    """Show interactive menu"""
    print("\n=== Frequency Test Menu ===")
    print("1. get_motor_status read frequency")
    print("2. set_finger_positions write frequency")
    print("3. Mixed function frequency")
    print("4. Stability test")
    print("0. Run all tests (1-4)")
    print("q. Quit")

    try:
        choice = input("\nSelect test: ").strip().lower()
        if choice == 'q':
            return None
        return int(choice)
    except ValueError:
        return -1


async def auto_detect_first_and_init():
    """Auto-detect and initialize the first available device."""
    logger.info("Auto-detecting the first available device...")

    devices = await sdk.auto_detect(scan_all=False)

    if not devices:
        logger.error("No devices found")
        return None, None, None

    logger.info(f"Found {len(devices)} device(s):")
    for i, dev in enumerate(devices):
        hw_name = get_hw_type_name(dev.hardware_type) if dev.hardware_type else "Unknown"
        print(f"\n[{i + 1}] {hw_name}")
        print(f"    Protocol: {get_protocol_display_name(dev.protocol_type)}")
        print(f"    Port: {dev.port_name}")
        print(f"    Slave ID: 0x{dev.slave_id:02X} ({dev.slave_id})")

    device = devices[0]
    logger.info("Using the first detected device")

    # Initialize context
    ctx = await sdk.init_from_detected(device)

    # Build connection info
    connection_info = ConnectionInfo(
        adapter_type=detect_adapter_type(device.port_name, device.protocol_type),
        protocol=get_protocol_display_name(device.protocol_type),
        port_name=device.port_name,
        slave_id=device.slave_id,
        baudrate=device.baudrate,
        data_baudrate=device.data_baudrate if hasattr(device, 'data_baudrate') else 0,
    )

    return ctx, device.slave_id, connection_info


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Communication Frequency Test")
    parser.add_argument("test_num", nargs="?", type=int, choices=range(0, 5), help="Test number (0=all, 1-4=specific)")
    parser.add_argument("--duration", type=float, default=5.0, help="Read/write/mixed test duration in seconds")
    parser.add_argument("--target-hz", type=float, default=1000.0, help="Read/mixed target rate; 0 runs at maximum throughput")
    parser.add_argument("--write-target-hz", type=float, default=50.0, help="Write target rate; 0 runs at maximum throughput")
    parser.add_argument("--stability-hz", type=float, default=100.0, help="Stability-test read rate")
    parser.add_argument("--stability-duration", type=float, default=60.0, help="Stability-test duration in seconds")
    parser.add_argument("--sample-interval", type=float, default=1.0, help="Stability aggregation interval in seconds")
    parser.add_argument("--warmup", type=float, default=1.0, help="Read-only warm-up duration in seconds")
    parser.add_argument("--max-count", type=int, default=10000, help="Maximum requests per frequency test")
    parser.add_argument("--progress-every", type=int, default=0, help="Log every N measured requests; 0 disables progress logging")
    parser.add_argument("--output", help="Write JSON results to this path")
    parser.add_argument("--yes", action="store_true", help="Acknowledge finger movement without an interactive prompt")
    args = parser.parse_args()

    if min(args.duration, args.target_hz, args.write_target_hz, args.stability_hz,
           args.stability_duration, args.warmup) < 0:
        parser.error("duration and frequency values must be non-negative")
    if args.sample_interval <= 0:
        parser.error("--sample-interval must be greater than zero")
    if args.max_count <= 0:
        parser.error("--max-count must be greater than zero")
    if args.progress_every < 0:
        parser.error("--progress-every must be non-negative")

    print("=== Communication Frequency Test ===\n")

    ctx, slave_id, connection_info = await auto_detect_first_and_init()
    if ctx is None:
        return

    config = TestConfig(
        test_duration=args.duration,
        max_test_count=args.max_count,
        target_frequency=args.target_hz,
        write_target_frequency=args.write_target_hz,
        stability_frequency=args.stability_hz,
        warmup_duration=args.warmup,
        stability_duration=args.stability_duration,
        sample_interval=args.sample_interval,
        progress_every=args.progress_every,
    )
    tester = CommFrequencyTester(ctx, slave_id, connection_info, config)
    collected = {"reports": [], "stability": None}

    try:
        await tester.warm_up()
        if args.test_num is not None:
            if not confirm_motion_test(args.test_num, args.yes):
                print("Test cancelled")
                return
            if args.test_num == 0:
                result_data = await tester.run_all_tests()
            else:
                result_data = await tester.run_test(args.test_num)
            collected["reports"].extend(result_data["reports"])
            collected["stability"] = result_data["stability"]
        else:
            # Interactive menu
            while True:
                choice = show_menu()
                if choice is None:
                    break
                elif choice == 0:
                    if not confirm_motion_test(choice, args.yes):
                        print("Test cancelled")
                        continue
                    result_data = await tester.run_all_tests()
                elif 1 <= choice <= 4:
                    if not confirm_motion_test(choice, args.yes):
                        print("Test cancelled")
                        continue
                    result_data = await tester.run_test(choice)
                else:
                    print("Invalid choice")
                    continue
                collected["reports"].extend(result_data["reports"])
                if result_data["stability"] is not None:
                    collected["stability"] = result_data["stability"]
    finally:
        await sdk.close_device_handler(ctx)
        logger.info("Device connection closed")

    if args.output:
        save_results(args.output, config, collected)

    print("\n=== Test completed ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUser interrupted")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
