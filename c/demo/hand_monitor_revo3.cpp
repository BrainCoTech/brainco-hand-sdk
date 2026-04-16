/**
 * @file hand_monitor_v3.cpp
 * @brief Revo3 (V3) Real-time Data Monitor
 *
 * Demonstrates DataCollector-based continuous data collection for Revo3:
 *
 * Modes:
 *   motor  - Motor-only (data_collector_new_v3_basic + CV3MotorStatusBuffer)
 *   touch  - Motor + Touch (data_collector_new_v3_full + CV3MotorStatusBuffer + CV3TouchDataBuffer)
 *
 * Build: make hand_monitor_v3.exe
 * Run:   ./hand_monitor_v3.exe              # Auto-detect, motor only
 *        ./hand_monitor_v3.exe touch        # Motor + touch (buffered)
 *        ./hand_monitor_v3.exe -m <port> 5000000 1 touch  # Manual init
 */

#include "stark-sdk.h"
#include "../common/stark_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

#define REVO3_MOTOR_COUNT 21
#define REVO3_TOUCH_MODULE_COUNT 11
#define REVO3_TOUCH_SUMMARY_COUNT 16

// Frequencies
#ifdef __linux__
  #define REVO3_MOTOR_FREQ 200
  #define REVO3_TOUCH_FREQ 10
#else
  #define REVO3_MOTOR_FREQ 100
  #define REVO3_TOUCH_FREQ 5
#endif

// Collection mode
typedef enum {
    REVO3_MODE_MOTOR = 0,
    REVO3_MODE_TOUCH,
} V3CollectionMode;

static const char *MODULE_NAMES[] = {
    "Palm",
    "ThTip", "ThPad",
    "IxTip", "IxPad",
    "MdTip", "MdPad",
    "RgTip", "RgPad",
    "PkTip", "PkPad",
};

static const char *PAD_NAMES[] = {
    "Palm",
    "Th.Tip", "Th.UPad", "Th.LPad",
    "Ix.Tip", "Ix.UPad", "Ix.LPad",
    "Md.Tip", "Md.UPad", "Md.LPad",
    "Rg.Tip", "Rg.UPad", "Rg.LPad",
    "Pk.Tip", "Pk.UPad", "Pk.LPad",
};

static volatile int keep_running = 1;

void signal_handler(int signum) {
    printf("\n[INFO] Received signal %d, stopping...\n", signum);
    keep_running = 0;
}

// ============================================================================
// V3 Motor-Only Collection Loop
// ============================================================================

void run_v3_motor_collection(
    CDataCollector* collector,
    CV3MotorStatusBuffer* motor_buffer
) {
    const int MAX_DATA = 2000;
    CV3MotorStatusData* data = (CV3MotorStatusData*)malloc(sizeof(CV3MotorStatusData) * MAX_DATA);
    if (!data) {
        fprintf(stderr, "[ERROR] Failed to allocate motor data array.\n");
        return;
    }

    int loop_count = 0;

    while (keep_running) {
        usleep(200 * 1000); // 200ms print interval
        loop_count++;

        size_t buffer_len = v3_motor_buffer_len(motor_buffer);
        if (buffer_len == 0) continue;

        int count = v3_motor_buffer_pop_all(motor_buffer, data, MAX_DATA);
        if (count <= 0) continue;

        auto latest = &data[count - 1];

        printf("[%3d] %d samples | buf=%zu\n", loop_count, count, buffer_len);

        printf("  Pos (M0~M4):  ");
        for (int i = 0; i < 5; i++) printf("%7.1f", latest->positions[i]);
        printf("\n");

        printf("  Vel (M0~M4):  ");
        for (int i = 0; i < 5; i++) printf("%7.1f", latest->velocities[i]);
        printf("\n");

        printf("  Cur (M0~M4):  ");
        for (int i = 0; i < 5; i++) printf("%7.3f", latest->currents[i]);
        printf("\n");

        // Print errors if any
        bool has_errors = false;
        for (int i = 0; i < REVO3_MOTOR_COUNT; i++) {
            if (latest->errors[i] != 0) {
                if (!has_errors) {
                    printf("  Errors: ");
                    has_errors = true;
                }
                printf("M%d=0x%04X ", i, latest->errors[i]);
            }
        }
        if (has_errors) printf("\n");
        printf("\n");
    }

    free(data);
}

// ============================================================================
// V3 Motor + Touch (Buffered) Collection Loop
// ============================================================================

void run_v3_full_collection(
    CDataCollector* collector,
    CV3MotorStatusBuffer* motor_buffer,
    CV3TouchDataBuffer* touch_buffer
) {
    const int MAX_MOTOR_DATA = 2000;
    const int MAX_TOUCH_DATA = 200;

    CV3MotorStatusData* motor_data =
        (CV3MotorStatusData*)malloc(sizeof(CV3MotorStatusData) * MAX_MOTOR_DATA);
    CV3TouchData* touch_data =
        (CV3TouchData*)malloc(sizeof(CV3TouchData) * MAX_TOUCH_DATA);

    if (!motor_data || !touch_data) {
        fprintf(stderr, "[ERROR] Failed to allocate data arrays.\n");
        free(motor_data);
        free(touch_data);
        return;
    }

    int loop_count = 0;

    while (keep_running) {
        usleep(200 * 1000); // 200ms
        loop_count++;

        // Motor data
        int motor_count = v3_motor_buffer_pop_all(motor_buffer, motor_data, MAX_MOTOR_DATA);

        // Touch data
        int touch_count = v3_touch_buffer_pop_all(touch_buffer, touch_data, MAX_TOUCH_DATA);

        printf("[%3d] Motor: %d | Touch: %d\n",
               loop_count,
               motor_count > 0 ? motor_count : 0,
               touch_count > 0 ? touch_count : 0);

        // Show motor snapshot
        if (motor_count > 0) {
            auto m = &motor_data[motor_count - 1];
            printf("Pos[0]=%6.1f, Spd[0]=%6.1f, Cur[0]=%6.1f \t | "
                   "Pos[20]=%6.1f, Spd[20]=%6.1f, Cur[20]=%6.1f\n",
                   m->positions[0], m->velocities[0], m->currents[0],
                   m->positions[20], m->velocities[20], m->currents[20]);
        }

        // Show touch snapshot
        if (touch_count > 0) {
            auto t = &touch_data[touch_count - 1];

            // Summary
            printf("  Summary:");
            for (int i = 0; i < REVO3_TOUCH_SUMMARY_COUNT; i++) {
                if (t->summary[i] > 0) {
                    printf(" %s=%u", PAD_NAMES[i], t->summary[i]);
                }
            }
            printf("\n");

            // Per-module stats
            for (int m = 0; m < REVO3_TOUCH_MODULE_COUNT; m++) {
                int pts = t->module_counts[m];
                if (pts == 0) continue;

                uint32_t sum = 0;
                uint16_t max_val = 0;
                for (int j = 0; j < pts; j++) {
                    sum += t->modules[m][j];
                    if (t->modules[m][j] > max_val) max_val = t->modules[m][j];
                }

                if (max_val > 0) {
                    printf("    %-6s (%2d pts): sum=%5u, max=%5u\n",
                           MODULE_NAMES[m], pts, sum, max_val);
                }
            }
        }
        printf("\n");
    }

    free(motor_data);
    free(touch_data);
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char *argv[]) {
    setup_signal_handlers();
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    printf("=== Revo3 Data Monitor ===\n\n");
    init_logging(LOG_LEVEL_INFO);

    DeviceContext ctx = {};
    int arg_idx = 0;
    if (!parse_args_and_init_revo3(&ctx, argc, (const char**)argv, &arg_idx)) {
        return 1;
    }

    // Verify V3 device
    if (!stark_uses_revo3_motor_api(ctx.hw_type)) {
        printf("[WARN] Device is not Revo3 (hw_type=%d). V3 APIs may not work.\n", ctx.hw_type);
    }

    // Parse mode from remaining args
    V3CollectionMode mode = REVO3_MODE_MOTOR;
    if (arg_idx < argc) {
        if (strcmp(argv[arg_idx], "touch") == 0) {
            mode = REVO3_MODE_TOUCH;
        }
    }

    printf("[INFO] Mode: %s\n", mode == REVO3_MODE_TOUCH ? "motor+touch (buffered)" : "motor");
    printf("[INFO] Motor frequency: %d Hz\n", REVO3_MOTOR_FREQ);
    if (mode == REVO3_MODE_TOUCH) {
        printf("[INFO] Touch frequency: %d Hz\n", REVO3_TOUCH_FREQ);
    }

    // Create V3 motor buffer
    auto motor_buffer = v3_motor_buffer_new(2000);
    if (!motor_buffer) {
        fprintf(stderr, "[ERROR] Failed to create V3 motor buffer.\n");
        cleanup_device_context(&ctx);
        return 1;
    }

    // Create V3 touch buffer (only for touch mode)
    CV3TouchDataBuffer* touch_buffer = NULL;
    if (mode == REVO3_MODE_TOUCH) {
        printf("[INFO] Enabling all touch modules...\n");
        stark_v3_set_all_touch_modules_enabled(ctx.handle, ctx.slave_id, 0x7FF);
        usleep(500 * 1000);

        touch_buffer = v3_touch_buffer_new(200);
        if (!touch_buffer) {
            fprintf(stderr, "[ERROR] Failed to create V3 touch buffer.\n");
            v3_motor_buffer_free(motor_buffer);
            cleanup_device_context(&ctx);
            return 1;
        }
    }

    // Create V3 data collector
    CDataCollector* collector = NULL;
    if (mode == REVO3_MODE_TOUCH) {
        collector = data_collector_new_v3_full(
            ctx.handle, motor_buffer, touch_buffer,
            ctx.slave_id, REVO3_MOTOR_FREQ, REVO3_TOUCH_FREQ, 1
        );
    } else {
        collector = data_collector_new_v3_basic(
            ctx.handle, motor_buffer, ctx.slave_id, REVO3_MOTOR_FREQ, 1
        );
    }

    if (!collector) {
        fprintf(stderr, "[ERROR] Failed to create V3 data collector.\n");
        if (touch_buffer) v3_touch_buffer_free(touch_buffer);
        v3_motor_buffer_free(motor_buffer);
        cleanup_device_context(&ctx);
        return 1;
    }

    // Start collection
    if (data_collector_start(collector) != 0) {
        fprintf(stderr, "[ERROR] Failed to start data collector.\n");
        data_collector_free(collector);
        if (touch_buffer) v3_touch_buffer_free(touch_buffer);
        v3_motor_buffer_free(motor_buffer);
        cleanup_device_context(&ctx);
        return 1;
    }

    printf("[INFO] Data collector started! Press Ctrl+C to stop...\n\n");

    // Run collection loop
    switch (mode) {
        case REVO3_MODE_MOTOR:
            run_v3_motor_collection(collector, motor_buffer);
            break;
        case REVO3_MODE_TOUCH:
            run_v3_full_collection(collector, motor_buffer, touch_buffer);
            break;
    }

    // Cleanup
    printf("[INFO] Stopping data collector...\n");
    data_collector_stop(collector);
    data_collector_free(collector);
    if (touch_buffer) v3_touch_buffer_free(touch_buffer);
    v3_motor_buffer_free(motor_buffer);
    cleanup_device_context(&ctx);

    printf("[INFO] Done!\n");
    return 0;
}
