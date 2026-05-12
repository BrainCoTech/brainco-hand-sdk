/**
 * @file hand_trajectory_revo3.cpp
 * @brief Stark Revo3 Trajectory Control & Teaching Mode Demo
 *
 * Demonstrates high-level motion APIs:
 *   - Quintic polynomial trajectory (move_joint / move_hand)
 *   - Teaching (backdrive) mode with recording (teach_joint / teach_hand)
 *   - Trajectory replay (replay_joint / replay_hand)
 *   - Position range protection
 *
 * Build: make hand_trajectory_revo3.exe
 * Run:   ./hand_trajectory_revo3.exe              # Auto-detect
 *        ./hand_trajectory_revo3.exe -m <port> 5000000 1
 */

#include "stark-sdk.h"
#include "../common/stark_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <math.h>

#define REVO3_MOTOR_COUNT 21
#define MAX_TEACH_SAMPLES 1000

static volatile int keep_running = 1;

void signal_handler(int signum) {
    printf("\n[INFO] Stopping...\n");
    keep_running = 0;
}

void msleep(int ms) {
    usleep(ms * 1000);
}

//=============================================================================
// Trajectory Control Demos
//=============================================================================

void demo_single_joint_move(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Single Joint Quintic Move ===\n");

    uint16_t joint_id = 3;  // Pinky DIP [0, 90°]
    float target = 45.0f;
    float duration = 2.0f;
    float dt = 0.01f;  // 100Hz

    printf("  Moving J%d to %.1f° over %.1fs...\n", joint_id, target, duration);
    int ret = stark_revo3_move_joint(handle, slave_id, joint_id, target, duration, dt);
    printf("  Result: %s\n", ret == 0 ? "✅ OK" : "❌ FAIL");

    // Verify
    msleep(200);
    CV3MotorStatusData *status = stark_v3_get_motor_status_data(handle, slave_id);
    if (status) {
        float error = fabsf(target - status->positions[joint_id]);
        printf("  Final: %.2f° (error: %.2f°) %s\n",
               status->positions[joint_id], error,
               error < 5.0f ? "✅" : "⚠️");
        free_v3_motor_status_data(status);
    }

    // Move back
    printf("  Moving J%d back to 0°...\n", joint_id);
    stark_revo3_move_joint(handle, slave_id, joint_id, 0.0f, duration, dt);
    msleep(500);
}

void demo_custom_gains_move(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Single Joint Move with Custom Gains ===\n");

    uint16_t joint_id = 1;  // Pinky MCP [0, 90°]
    float target = 60.0f;
    float kp = 5.0f, kd = 0.5f;

    printf("  J%d: target=%.1f°, Kp=%.1f, Kd=%.1f, T=1.5s\n",
           joint_id, target, kp, kd);
    int ret = stark_revo3_move_joint_with_gains(
        handle, slave_id, joint_id, target, 1.5f, 0.01f, kp, kd);
    printf("  Result: %s\n", ret == 0 ? "✅ OK" : "❌ FAIL");

    // Move back
    stark_revo3_move_joint(handle, slave_id, joint_id, 0.0f, 1.5f, 0.01f);
    msleep(500);
}

void demo_full_hand_move(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Full Hand Move ===\n");

    float targets[REVO3_MOTOR_COUNT];
    memset(targets, 0, sizeof(targets));

    // Set MCP joints to 45°
    int mcp_joints[] = {1, 5, 9, 13, 17};
    int n_mcp = sizeof(mcp_joints) / sizeof(mcp_joints[0]);
    for (int i = 0; i < n_mcp; i++) {
        targets[mcp_joints[i]] = 45.0f;
    }

    printf("  MCP joints → 45°, T=3.0s\n");
    int ret = stark_revo3_move_hand(
        handle, slave_id, targets, REVO3_MOTOR_COUNT, 3.0f, 0.01f);
    printf("  Result: %s\n", ret == 0 ? "✅ OK" : "❌ FAIL");

    // Verify
    msleep(500);
    CV3MotorStatusData *status = stark_v3_get_motor_status_data(handle, slave_id);
    if (status) {
        printf("  Final MCP positions:\n");
        for (int i = 0; i < n_mcp; i++) {
            int jid = mcp_joints[i];
            float err = fabsf(targets[jid] - status->positions[jid]);
            printf("    J%2d: %.2f° (err=%.2f°) %s\n",
                   jid, status->positions[jid], err,
                   err < 5.0f ? "✅" : "⚠️");
        }
        free_v3_motor_status_data(status);
    }

    // Reset
    printf("  Resetting to 0°...\n");
    float zeros[REVO3_MOTOR_COUNT];
    memset(zeros, 0, sizeof(zeros));
    stark_revo3_move_hand(handle, slave_id, zeros, REVO3_MOTOR_COUNT, 3.0f, 0.01f);
    msleep(500);
}

void demo_position_protection(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Position Range Protection ===\n");

    // J0 (Pinky Abd, range [-14, 15]) to 50° — should fail
    printf("  J0 → 50° (range: [-14, 15])...\n");
    int ret = stark_revo3_move_joint(handle, slave_id, 0, 50.0f, 1.0f, 0.01f);
    printf("  %s\n", ret != 0 ? "✅ Correctly rejected" : "⚠️ Unexpectedly accepted");

    // J20 (Thumb CMC Flex, range [0, 75]) to -10° — should fail
    printf("  J20 → -10° (range: [0, 75])...\n");
    ret = stark_revo3_move_joint(handle, slave_id, 20, -10.0f, 1.0f, 0.01f);
    printf("  %s\n", ret != 0 ? "✅ Correctly rejected" : "⚠️ Unexpectedly accepted");
}

//=============================================================================
// Teaching Mode Demos
//=============================================================================

void demo_teach_and_replay_joint(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Single Joint Teaching & Replay ===\n");

    uint16_t joint_id = 3;  // Pinky DIP
    float dt = 0.02f;         // 50Hz
    float duration = 5.0f;

    printf("  Teaching J%d: move the joint freely for %.1fs...\n", joint_id, duration);
    printf("  Recording starts NOW!\n\n");

    float recorded[MAX_TEACH_SAMPLES];
    uint32_t count = 0;

    int ret = stark_revo3_teach_joint(
        handle, slave_id, joint_id, dt, duration,
        recorded, MAX_TEACH_SAMPLES, &count);

    if (ret == 0 && count > 0) {
        // Find min/max
        float min_pos = recorded[0], max_pos = recorded[0];
        for (uint32_t i = 1; i < count; i++) {
            if (recorded[i] < min_pos) min_pos = recorded[i];
            if (recorded[i] > max_pos) max_pos = recorded[i];
        }

        printf("  Recorded %u samples\n", count);
        printf("  Range: %.2f° .. %.2f°\n", min_pos, max_pos);
        printf("  Start: %.2f°, End: %.2f°\n", recorded[0], recorded[count - 1]);

        // Print some samples
        uint32_t step = count > 10 ? count / 8 : 1;
        printf("\n    Time(s) | Position(°)\n");
        printf("    --------|------------\n");
        for (uint32_t i = 0; i < count; i += step) {
            printf("    %6.2f  | %8.2f\n", i * dt, recorded[i]);
        }

        // Replay
        printf("\n  Replaying %u samples...\n", count);
        msleep(2000);

        ret = stark_revo3_replay_joint(
            handle, slave_id, joint_id,
            recorded, count, dt, 3.0f, 0.3f);
        printf("  Replay: %s\n", ret == 0 ? "✅ OK" : "❌ FAIL");
    } else {
        printf("  Teaching failed (ret=%d)\n", ret);
    }

    // Reset
    stark_revo3_move_joint(handle, slave_id, joint_id, 0.0f, 2.0f, 0.01f);
    msleep(500);
}

void demo_teach_and_replay_hand(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Full Hand Teaching & Replay ===\n");

    float dt = 0.02f;
    float duration = 5.0f;

    printf("  Teaching all joints: move the hand freely for %.1fs...\n", duration);
    printf("  Recording starts NOW!\n\n");

    float trajectory[MAX_TEACH_SAMPLES * REVO3_MOTOR_COUNT];
    uint32_t count = 0;

    int ret = stark_revo3_teach_hand(
        handle, slave_id, dt, duration,
        REVO3_MOTOR_COUNT,
        trajectory, MAX_TEACH_SAMPLES, &count);

    if (ret == 0 && count > 0) {
        printf("  Recorded %u frames (%.1fs)\n", count, count * dt);

        // Show start vs end for MCP joints
        int mcp_joints[] = {1, 5, 9, 13, 17};
        const char *names[] = {"Pinky", "Ring", "Mid", "Index", "Thumb"};
        int n_mcp = 5;

        printf("\n    Joint     | Start(°) | End(°)  | Delta(°)\n");
        printf("    ----------|----------|---------|----------\n");
        for (int k = 0; k < n_mcp; k++) {
            int jid = mcp_joints[k];
            float s = trajectory[0 * REVO3_MOTOR_COUNT + jid];
            float e = trajectory[(count - 1) * REVO3_MOTOR_COUNT + jid];
            printf("    J%2d %-6s| %7.2f  | %6.2f  | %+7.2f\n",
                   jid, names[k], s, e, e - s);
        }

        // Replay
        printf("\n  Replaying %u frames...\n", count);
        msleep(2000);

        ret = stark_revo3_replay_hand(
            handle, slave_id,
            trajectory, count, REVO3_MOTOR_COUNT,
            dt, 3.0f, 0.3f);
        printf("  Replay: %s\n", ret == 0 ? "✅ OK" : "❌ FAIL");
    } else {
        printf("  Teaching failed (ret=%d)\n", ret);
    }

    // Reset
    float zeros[REVO3_MOTOR_COUNT];
    memset(zeros, 0, sizeof(zeros));
    stark_revo3_move_hand(handle, slave_id, zeros, REVO3_MOTOR_COUNT, 3.0f, 0.01f);
    msleep(500);
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

    printf("=== Revo3 Trajectory Control & Teaching Demo ===\n");

    // Trajectory control demos
    demo_single_joint_move(ctx.handle, ctx.slave_id);
    demo_custom_gains_move(ctx.handle, ctx.slave_id);
    demo_full_hand_move(ctx.handle, ctx.slave_id);
    demo_position_protection(ctx.handle, ctx.slave_id);

    // Teaching demos
    demo_teach_and_replay_joint(ctx.handle, ctx.slave_id);
    demo_teach_and_replay_hand(ctx.handle, ctx.slave_id);

    // Cleanup
    printf("\nDone. Closing...\n");
    cleanup_device_context(&ctx);
    return 0;
}
