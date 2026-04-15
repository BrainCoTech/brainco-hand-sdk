#!/usr/bin/env python3
"""
Stark Revo3 (V3) Touch / Tactile Sensor Demo

Demonstrates V3-specific touch sensor APIs:
  - Enable/disable touch modules (11 modules: palm + 5 fingers × 2 pads)
  - Set data output type (AD raw / calibrated)
  - Read summary force values (16 pads)
  - Read single module pressure array data
  - Read all touch data (summary + all 11 module arrays)
  - Clear pressure data (per-module or global)

Module Map (0~10):
  0: Palm
  1: ThumbTip,   2: ThumbPad
  3: IndexTip,   4: IndexPad
  5: MiddleTip,  6: MiddlePad
  7: RingTip,    8: RingPad
  9: PinkyTip,  10: PinkyPad

Summary Layout (16 values):
  [0] palm
  [1] thumb tip,  [2] thumb upper pad,  [3] thumb lower pad
  [4] index tip,  [5] index upper pad,  [6] index lower pad
  [7] middle tip, [8] middle upper pad, [9] middle lower pad
  [10] ring tip,  [11] ring upper pad,  [12] ring lower pad
  [13] pinky tip, [14] pinky upper pad, [15] pinky lower pad

Run:
    python hand_touch_revo3.py              # Auto-detect
    python hand_touch_revo3.py -m <port> 5000000 1  # Manual Modbus
"""

import asyncio
import sys
import os
import argparse

# Setup path and imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import sdk, check_sdk, logger
from common_init import (
    DeviceContext, parse_args_and_init, cleanup_context,
    auto_detect_and_init
)

check_sdk()

REVO3_TOUCH_MODULE_COUNT = 11
REVO3_TOUCH_MODULE_NAMES = [
    "Palm",
    "ThumbTip",  "ThumbPad",
    "IndexTip",  "IndexPad",
    "MiddleTip", "MiddlePad",
    "RingTip",   "RingPad",
    "PinkyTip",  "PinkyPad",
]

SUMMARY_PAD_NAMES = [
    "Palm",
    "Thumb Tip", "Thumb Upper Pad", "Thumb Lower Pad",
    "Index Tip", "Index Upper Pad", "Index Lower Pad",
    "Middle Tip", "Middle Upper Pad", "Middle Lower Pad",
    "Ring Tip", "Ring Upper Pad", "Ring Lower Pad",
    "Pinky Tip", "Pinky Upper Pad", "Pinky Lower Pad",
]


async def demo_device_info(ctx, slave_id):
    """Read and display V3 device information"""
    print("\n=== Device Info ===")

    sn = await ctx.get_device_sn(slave_id)
    print(f"  Serial Number: {sn}")

    fw = await ctx.get_device_fw_version(slave_id)
    print(f"  Firmware: {fw}")


async def demo_enable_modules(ctx, slave_id):
    """Enable/disable touch modules"""
    print("\n=== Touch Module Enable/Disable ===")

    # Enable all 11 modules at once (bits 0~10 = 0x7FF)
    all_bits = 0x7FF
    print(f"  Enabling all modules: 0x{all_bits:03X} ({all_bits:011b})")
    await ctx.v3_set_all_touch_modules_enabled(slave_id, all_bits)
    await asyncio.sleep(0.5)

    # Read back enable state
    enabled_bits = await ctx.v3_get_all_touch_modules_enabled(slave_id)
    print(f"  Enabled modules: 0x{enabled_bits:03X} ({enabled_bits:011b})")
    for i in range(REVO3_TOUCH_MODULE_COUNT):
        state = "ON" if (enabled_bits & (1 << i)) else "OFF"
        print(f"    [{i:2d}] {REVO3_TOUCH_MODULE_NAMES[i]:12s}: {state}")

    # Enable/disable a single module (example: toggle Palm)
    print("\n  --- Single module toggle (Palm) ---")
    is_enabled = await ctx.v3_get_touch_module_enabled(slave_id, 0)
    print(f"  Palm enabled: {is_enabled}")

    # Disable Palm
    await ctx.v3_set_touch_module_enabled(slave_id, 0, False)
    is_enabled = await ctx.v3_get_touch_module_enabled(slave_id, 0)
    print(f"  Palm enabled (after disable): {is_enabled}")

    # Re-enable Palm
    await ctx.v3_set_touch_module_enabled(slave_id, 0, True)
    is_enabled = await ctx.v3_get_touch_module_enabled(slave_id, 0)
    print(f"  Palm enabled (after re-enable): {is_enabled}")


async def demo_data_type(ctx, slave_id):
    """Set and read touch data output type"""
    print("\n=== Touch Data Type ===")

    # Read current data type
    data_type = await ctx.v3_get_touch_data_type(slave_id)
    print(f"  Current data type: {data_type} ({'Calibrated' if data_type == 1 else 'AD Raw'})")

    # Set to calibrated value
    print("  Setting data type to calibrated (1)...")
    await ctx.v3_set_touch_data_type(slave_id, 1)
    data_type = await ctx.v3_get_touch_data_type(slave_id)
    print(f"  Data type after set: {data_type} ({'Calibrated' if data_type == 1 else 'AD Raw'})")

    # Set to AD raw value
    print("  Setting data type to AD raw (0)...")
    await ctx.v3_set_touch_data_type(slave_id, 0)
    data_type = await ctx.v3_get_touch_data_type(slave_id)
    print(f"  Data type after set: {data_type} ({'Calibrated' if data_type == 1 else 'AD Raw'})")


async def demo_read_summary(ctx, slave_id):
    """Read summary force values for all pads"""
    print("\n=== Touch Summary (16 pads) ===")

    summary = await ctx.v3_get_touch_summary(slave_id)
    print(f"  Raw values: {summary}")
    for i, val in enumerate(summary):
        name = SUMMARY_PAD_NAMES[i] if i < len(SUMMARY_PAD_NAMES) else f"Pad[{i}]"
        bar = "█" * min(val // 100, 30)  # simple bar chart
        print(f"  [{i:2d}] {name:20s}: {val:5d}  {bar}")


async def demo_read_module_data(ctx, slave_id):
    """Read pressure array data for individual modules"""
    print("\n=== Single Module Pressure Data ===")

    # Read data from each module
    for module_id in range(REVO3_TOUCH_MODULE_COUNT):
        data = await ctx.v3_get_touch_module_data(slave_id, module_id)
        name = REVO3_TOUCH_MODULE_NAMES[module_id]
        total = sum(data)
        print(f"  [{module_id:2d}] {name:12s} ({len(data):2d} pts): "
              f"sum={total:6d}, max={max(data):5d}, min={min(data):5d}")


async def demo_read_all_data(ctx, slave_id):
    """Read all touch data at once (summary + all modules)"""
    print("\n=== All Touch Data ===")

    touch_data = await ctx.v3_get_all_touch_data(slave_id)

    print(f"  Summary ({len(touch_data.summary)} values): {touch_data.summary}")
    print(f"  Modules: {len(touch_data.modules)}")
    for i, module_data in enumerate(touch_data.modules):
        name = REVO3_TOUCH_MODULE_NAMES[i] if i < REVO3_TOUCH_MODULE_COUNT else f"Module[{i}]"
        total = sum(module_data) if module_data else 0
        print(f"    [{i:2d}] {name:12s}: {len(module_data):2d} pts, sum={total}")


async def demo_clear_pressure(ctx, slave_id):
    """Clear pressure data"""
    print("\n=== Clear Pressure Data ===")

    # Clear a single module (Palm)
    print("  Clearing Palm (module 0) pressure data...")
    await ctx.v3_reset_touch_pressure(slave_id, 0)
    await asyncio.sleep(0.1)

    # Clear all modules
    print("  Clearing all modules pressure data...")
    await ctx.v3_reset_all_touch_pressure(slave_id)
    await asyncio.sleep(0.1)

    print("  Pressure data cleared.")


async def demo_continuous_monitor(ctx, slave_id, count=10, interval=0.1):
    """Continuous touch monitoring (summary only)"""
    print(f"\n=== Continuous Monitor ({count} reads, {interval}s interval) ===")

    for i in range(count):
        summary = await ctx.v3_get_touch_summary(slave_id)
        # Format as compact string
        vals = " ".join(f"{v:4d}" for v in summary)
        print(f"  [{i:3d}] {vals}")
        await asyncio.sleep(interval)


async def main():
    device_ctx, extra_args, _ = await parse_args_and_init(sys.argv)
    if device_ctx is None:
        return

    ctx = device_ctx.ctx
    slave_id = device_ctx.slave_id

    # Verify V3 device
    if not ctx.uses_revo3_motor_api(slave_id):
        print(f"Warning: Device is not Revo3 (hw_type={device_ctx.hw_type})")
        print("V3 Touch APIs may not work correctly on this device.")

    try:
        await demo_device_info(ctx, slave_id)
        await demo_enable_modules(ctx, slave_id)
        await demo_data_type(ctx, slave_id)
        await demo_read_summary(ctx, slave_id)
        await demo_read_module_data(ctx, slave_id)
        await demo_read_all_data(ctx, slave_id)
        await demo_clear_pressure(ctx, slave_id)
        await demo_continuous_monitor(ctx, slave_id, count=5)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await cleanup_context(device_ctx)
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
