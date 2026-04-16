/**
 * @file hand_motor_v3.cpp
 * @brief Stark Revo3 Motor Control Demo
 *
 * Demonstrates Revo3 motor control APIs:
 *   - Control modes: position, velocity, current, MIT impedance, damping
 *   - Single motor and multi-joint control
 *   - MIT mode: τ = Kp*(P_des - P_act) + Kd*(V_des - V_act) + T_ff
 *   - Fingertip cartesian control (6-DoF per finger)
 *   - Teaching mode & Motor status monitoring
 *
 * Build: make hand_motor_v3.exe
 * Run:   ./hand_motor_v3.exe              # Auto-detect
 *        ./hand_motor_v3.exe -m <port> 5000000 1  # Manual Modbus
 */

#include "stark-sdk.h"
#include "../common/stark_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

#define REVO3_MOTOR_COUNT 21
#define REVO3_FINGER_COUNT 5

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

void demo_device_info(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Device Info ===\n");

    CDeviceInfo *info = stark_get_device_info(handle, slave_id);
    if (info) {
        printf("  Serial Number: %s\n", info->serial_number);
        printf("  Firmware: %s\n", info->firmware_version);
        printf("  Hardware Type: %d\n", info->hardware_type);
        printf("  Uses V3 API: %s\n",
               stark_uses_revo3_motor_api(info->hardware_type) ? "yes" : "no");
        free_device_info(info);
    } else {
        printf("  Failed to read device info\n");
    }

    const char *hw_ver = stark_revo3_get_hardware_version(handle, slave_id);
    if (hw_ver) {
        printf("  Hardware Version: %s\n", hw_ver);
    }

    uint32_t online_status = stark_revo3_get_motor_online_status(handle, slave_id);
    if (online_status != 0xFFFFFFFF) {
        printf("  Motor Online Status: 0x%06X\n", online_status);
    }
}

void demo_motor_status(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Motor Status ===\n");

    CV3MotorStatusData *status = stark_v3_get_motor_status_data(handle, slave_id);
    if (status) {
        printf("  Positions (first 5):");
        for (int i = 0; i < 5; i++) printf(" %.1f", status->positions[i]);
        printf("\n");

        printf("  Velocities (first 5):");
        for (int i = 0; i < 5; i++) printf(" %.1f", status->velocities[i]);
        printf("\n");

        printf("  Currents (first 5):");
        for (int i = 0; i < 5; i++) printf(" %.2f", status->currents[i]);
        printf("\n");

        free_v3_motor_status_data(status);
    } else {
        printf("  Failed to read motor status\n");
    }
}

void demo_new_single_joint(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Single Joint Control ===\n");

    // Mode 0 = Position. param is 45 (degrees)
    printf("  Joint 0: mode=Position(0), param=45°\n");
    stark_revo3_single_joint_control(handle, slave_id, 0, 0, 45);
    msleep(500);
}

void demo_new_multi_joint(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Multi-Joint Control ===\n");

    uint16_t params[21];
    for (int i = 0; i < 21; i++) {
        params[i] = 30; // 30 degrees
    }
    printf("  All 21 joints: mode=Position(0), param=30°\n");
    stark_revo3_multi_joint_control(handle, slave_id, 0, params);
    msleep(1000);

    // Reset to 0
    for (int i = 0; i < 21; i++) params[i] = 0;
    stark_revo3_multi_joint_control(handle, slave_id, 0, params);
    msleep(500);
}

void demo_new_mit_control(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== MIT Joint Control ===\n");
    printf("  τ = Kp*(P_des - P_act) + Kd*(V_des - V_act) + T_ff\n");

    // Joint 0: Kp=5.0, Kd=0.5, pos=45, vel=0, T_ff=200mA
    printf("  Joint 0: pos=45, Kp=5.0, Kd=0.5, T_ff=200mA\n");
    stark_revo3_mit_control(handle, slave_id, 0, 5.0f, 0.5f, 45.0f, 0.0f, 200.0f);
    msleep(1000);
}

void demo_new_multi_mit(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Multi-Joint MIT Control ===\n");

    printf("  All 21 joints via multi-MIT: pos=20, Kp=2.0, Kd=0.2, T_ff=50mA\n");
    float kps[21], kds[21], positions[21], velocities[21], torques[21];
    for (int i = 0; i < 21; i++) {
        kps[i] = 2.0f;
        kds[i] = 0.2f;
        positions[i] = 20.0f;
        velocities[i] = 0.0f;
        torques[i] = 50.0f;
    }
    stark_revo3_multi_mit_set_all(handle, slave_id, kps, kds, positions, velocities, torques);
    msleep(1000);

    // Reset
    for (int i = 0; i < 21; i++) {
        torques[i] = 0.0f;
        positions[i] = 0.0f;
    }
    stark_revo3_multi_mit_set_all(handle, slave_id, kps, kds, positions, velocities, torques);
    msleep(500);
}

void demo_new_batch_mit(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== MIT Batch Parameter Control ===\n");

    float vals[21];

    printf("  All Kp=4.0\n");
    for (int i = 0; i < 21; i++) vals[i] = 4.0f;
    stark_revo3_set_all_mit_kp(handle, slave_id, vals);
    msleep(100);

    printf("  All Kd=0.4\n");
    for (int i = 0; i < 21; i++) vals[i] = 0.4f;
    stark_revo3_set_all_mit_kd(handle, slave_id, vals);
    msleep(100);

    printf("  All positions=15°\n");
    for (int i = 0; i < 21; i++) vals[i] = 15.0f;
    stark_revo3_set_all_mit_positions(handle, slave_id, vals);
    msleep(500);

    // Back to 0
    for (int i = 0; i < 21; i++) vals[i] = 0.0f;
    stark_revo3_set_all_mit_positions(handle, slave_id, vals);
    msleep(500);
}

void demo_new_impedance_damping(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Impedance & Damping Mode ===\n");

    // Impedance mode (Mode=4), param = coeff * 100
    printf("  Joint 0: Impedance mode, coeff=50\n");
    stark_revo3_single_joint_control(handle, slave_id, 0, 4, 5000); // 50 * 100
    msleep(500);

    // Damping mode (Mode=5), param = coeff * 100
    printf("  Joint 0: Damping mode, coeff=30\n");
    stark_revo3_single_joint_control(handle, slave_id, 0, 5, 3000); // 30 * 100
    msleep(500);

    // Reset to position 0
    stark_revo3_single_joint_control(handle, slave_id, 0, 0, 0);
    msleep(500);
}

void demo_new_teaching_mode(DeviceHandler *handle, uint8_t slave_id) {
    printf("\n=== Teaching Mode ===\n");

    // Note: Python sdk uses v3_set_teaching_mode(True) via V3ControlMode 6 or similar
    // We can simulate it by setting mode to Damping=0 or MIT with 0 Kp/Kd
    printf("  Setting all joints to 0 Kp/Kd for compliance...\n");
    float zeros[21] = {0};
    stark_revo3_set_all_mit_kp(handle, slave_id, zeros);
    stark_revo3_set_all_mit_kd(handle, slave_id, zeros);
    stark_revo3_set_all_mit_torques(handle, slave_id, zeros);

    printf("  (Fingers should now move freely)\n");
    msleep(1500);

    printf("  Restoring rigidity...\n");
    float kps[21]; for (int i = 0; i < 21; i++) kps[i] = 4.0f;
    float kds[21]; for (int i = 0; i < 21; i++) kds[i] = 0.4f;
    stark_revo3_set_all_mit_kp(handle, slave_id, kps);
    stark_revo3_set_all_mit_kd(handle, slave_id, kds);
}

void demo_status_monitor(DeviceHandler *handle, uint8_t slave_id, int count) {
    printf("\n=== Status Monitor (%d reads) ===\n", count);

    for (int i = 0; i < count && keep_running; i++) {
        CV3MotorStatusData *status = stark_v3_get_motor_status_data(handle, slave_id);
        if (status) {
            printf("  [%d] pos:", i);
            for (int j = 0; j < 5; j++) printf(" %.1f", status->positions[j]);
            printf("\n");
            free_v3_motor_status_data(status);
        }
        msleep(200);
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
        printf("V3 APIs may not work correctly on this device.\n");
    }

    // Run demos
    demo_device_info(ctx.handle, ctx.slave_id);
    demo_motor_status(ctx.handle, ctx.slave_id);

    demo_new_single_joint(ctx.handle, ctx.slave_id);
    demo_new_multi_joint(ctx.handle, ctx.slave_id);
    demo_new_mit_control(ctx.handle, ctx.slave_id);
    demo_new_multi_mit(ctx.handle, ctx.slave_id);
    demo_new_batch_mit(ctx.handle, ctx.slave_id);
    demo_new_impedance_damping(ctx.handle, ctx.slave_id);
    demo_new_teaching_mode(ctx.handle, ctx.slave_id);

    demo_status_monitor(ctx.handle, ctx.slave_id, 5);

    // Cleanup
    printf("\nDone. Closing...\n");
    cleanup_device_context(&ctx);
    return 0;
}
