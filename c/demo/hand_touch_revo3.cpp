/**
 * @file hand_touch_v3.cpp
 * @brief Stark Revo3 (V3) Touch / Tactile Sensor Demo
 *
 * Demonstrates V3-specific touch sensor APIs:
 *   - Enable/disable touch modules (11 modules: palm + 5 fingers × 2 pads)
 *   - Set data output type (AD raw / calibrated)
 *   - Read summary force values (16 pads)
 *   - Read single module pressure array data
 *   - Clear pressure data (per-module or global)
 *
 * Module Map (0~10):
 *   0: Palm
 *   1: ThumbTip,   2: ThumbPad
 *   3: IndexTip,   4: IndexPad
 *   5: MiddleTip,  6: MiddlePad
 *   7: RingTip,    8: RingPad
 *   9: PinkyTip,  10: PinkyPad
 *
 * Summary Layout (16 values):
 *   [0] palm
 *   [1] thumb tip,  [2] thumb upper pad,  [3] thumb lower pad
 *   [4] index tip,  [5] index upper pad,  [6] index lower pad
 *   [7] middle tip, [8] middle upper pad, [9] middle lower pad
 *   [10] ring tip,  [11] ring upper pad,  [12] ring lower pad
 *   [13] pinky tip, [14] pinky upper pad, [15] pinky lower pad
 *
 * Build: make hand_touch_v3.exe
 * Run:   ./hand_touch_v3.exe              # Auto-detect
 *        ./hand_touch_v3.exe -m <port> 5000000 1  # Manual Modbus
 */

#include "stark-sdk.h"
#include "../common/stark_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

#define REVO3_TOUCH_MODULE_COUNT 11
#define REVO3_TOUCH_SUMMARY_COUNT 16

static const char *MODULE_NAMES[] = {
    "Palm",
    "ThumbTip",  "ThumbPad",
    "IndexTip",  "IndexPad",
    "MiddleTip", "MiddlePad",
    "RingTip",   "RingPad",
    "PinkyTip",  "PinkyPad",
};

static const char *SUMMARY_PAD_NAMES[] = {
    "Palm",
    "Thumb Tip", "Thumb Upper Pad", "Thumb Lower Pad",
    "Index Tip", "Index Upper Pad", "Index Lower Pad",
    "Middle Tip", "Middle Upper Pad", "Middle Lower Pad",
    "Ring Tip", "Ring Upper Pad", "Ring Lower Pad",
    "Pinky Tip", "Pinky Upper Pad", "Pinky Lower Pad",
};

static volatile int keep_running = 1;

void signal_handler(int signum) {
    printf("\n[INFO] Stopping...\n");
    keep_running = 0;
}

void msleep(int ms) {
    usleep(ms * 1000);
}

//=============================================================================
// Demo Functions
//=============================================================================

void demo_enable_modules(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Touch Module Enable/Disable ===\n");

    // Enable all 11 modules at once (bits 0~10 = 0x7FF)
    uint16_t all_bits = 0x7FF;
    printf("  Enabling all modules: 0x%03X\n", all_bits);
    stark_v3_set_all_touch_modules_enabled(handle, slave_id, all_bits);
    msleep(500);

    // Read back enable state
    uint16_t enabled_bits = stark_v3_get_all_touch_modules_enabled(handle, slave_id);
    printf("  Enabled modules: 0x%03X\n", enabled_bits);
    for (int i = 0; i < REVO3_TOUCH_MODULE_COUNT; i++) {
        const char *state = (enabled_bits & (1 << i)) ? "ON" : "OFF";
        printf("    [%2d] %-12s: %s\n", i, MODULE_NAMES[i], state);
    }

    // Toggle single module (Palm)
    printf("\n  --- Single module toggle (Palm) ---\n");
    int is_enabled = stark_v3_get_touch_module_enabled(handle, slave_id, 0);
    printf("  Palm enabled: %d\n", is_enabled);

    // Disable Palm
    stark_v3_set_touch_module_enabled(handle, slave_id, 0, false);
    msleep(100);
    is_enabled = stark_v3_get_touch_module_enabled(handle, slave_id, 0);
    printf("  Palm enabled (after disable): %d\n", is_enabled);

    // Re-enable Palm
    stark_v3_set_touch_module_enabled(handle, slave_id, 0, true);
    msleep(100);
    is_enabled = stark_v3_get_touch_module_enabled(handle, slave_id, 0);
    printf("  Palm enabled (after re-enable): %d\n", is_enabled);
}

void demo_data_type(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Touch Data Type ===\n");

    int data_type = stark_v3_get_touch_data_type(handle, slave_id);
    printf("  Current data type: %d (%s)\n", data_type,
           data_type == 1 ? "Calibrated" : "AD Raw");

    // Set to calibrated
    printf("  Setting data type to calibrated (1)...\n");
    stark_v3_set_touch_data_type(handle, slave_id, 1);
    msleep(100);
    data_type = stark_v3_get_touch_data_type(handle, slave_id);
    printf("  Data type after set: %d (%s)\n", data_type,
           data_type == 1 ? "Calibrated" : "AD Raw");

    // Set to AD raw
    printf("  Setting data type to AD raw (0)...\n");
    stark_v3_set_touch_data_type(handle, slave_id, 0);
    msleep(100);
    data_type = stark_v3_get_touch_data_type(handle, slave_id);
    printf("  Data type after set: %d (%s)\n", data_type,
           data_type == 1 ? "Calibrated" : "AD Raw");
}

void demo_read_summary(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Touch Summary (16 pads) ===\n");

    uint16_t summary[REVO3_TOUCH_SUMMARY_COUNT];
    if (stark_v3_get_touch_summary(handle, slave_id, summary) == 0) {
        for (int i = 0; i < REVO3_TOUCH_SUMMARY_COUNT; i++) {
            printf("  [%2d] %-20s: %5u\n", i, SUMMARY_PAD_NAMES[i], summary[i]);
        }
    } else {
        printf("  Failed to read touch summary\n");
    }
}

void demo_read_module_data(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Single Module Pressure Data ===\n");

    for (int module_id = 0; module_id < REVO3_TOUCH_MODULE_COUNT; module_id++) {
        uint16_t data[64];  // max buffer (palm has ~46 points)
        uint16_t count = 0;

        if (stark_v3_get_touch_module_data(handle, slave_id, module_id, data, &count) == 0) {
            // Calculate sum and max
            uint32_t sum = 0;
            uint16_t max_val = 0;
            uint16_t min_val = 0xFFFF;
            for (int i = 0; i < count; i++) {
                sum += data[i];
                if (data[i] > max_val) max_val = data[i];
                if (data[i] < min_val) min_val = data[i];
            }
            printf("  [%2d] %-12s (%2d pts): sum=%6u, max=%5u, min=%5u\n",
                   module_id, MODULE_NAMES[module_id], count, sum, max_val, min_val);
        } else {
            printf("  [%2d] %-12s: read failed\n", module_id, MODULE_NAMES[module_id]);
        }
    }
}

void demo_clear_pressure(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Clear Pressure Data ===\n");

    // Clear single module (Palm)
    printf("  Clearing Palm (module 0) pressure data...\n");
    stark_v3_reset_touch_pressure(handle, slave_id, 0);
    msleep(100);

    // Clear all modules
    printf("  Clearing all modules pressure data...\n");
    stark_v3_reset_all_touch_pressure(handle, slave_id);
    msleep(100);

    printf("  Pressure data cleared.\n");
}

void demo_continuous_monitor(DeviceHandler *handle, uint8_t slave_id, int count) {
    printf("\n=== Continuous Monitor (%d reads) ===\n", count);

    uint16_t summary[REVO3_TOUCH_SUMMARY_COUNT];
    for (int i = 0; i < count && keep_running; i++) {
        if (stark_v3_get_touch_summary(handle, slave_id, summary) == 0) {
            printf("  [%3d]", i);
            for (int j = 0; j < REVO3_TOUCH_SUMMARY_COUNT; j++) {
                printf(" %4u", summary[j]);
            }
            printf("\n");
        }
        msleep(100);
    }
}

//=============================================================================
// Main
//=============================================================================

int main(int argc, char *argv[]) {
    signal(SIGINT, signal_handler);
    init_logging(LOG_LEVEL_INFO);

    DeviceContext ctx = {};
    int arg_idx = 0;
    if (!parse_args_and_init_revo3(&ctx, argc, (const char**)argv, &arg_idx)) {
        return 1;
    }

    // Verify V3 device
    if (!stark_uses_revo3_motor_api(ctx.hw_type)) {
        printf("Warning: Device is not Revo3 (hw_type=%d)\n", ctx.hw_type);
        printf("V3 Touch APIs may not work correctly on this device.\n");
    }

    // Run demos
    demo_enable_modules(ctx.handle, ctx.slave_id);
    demo_data_type(ctx.handle, ctx.slave_id);
    demo_read_summary(ctx.handle, ctx.slave_id);
    demo_read_module_data(ctx.handle, ctx.slave_id);
    demo_clear_pressure(ctx.handle, ctx.slave_id);
    demo_continuous_monitor(ctx.handle, ctx.slave_id, 5);

    // Cleanup
    printf("\nDone. Closing...\n");
    cleanup_device_context(&ctx);
    return 0;
}
