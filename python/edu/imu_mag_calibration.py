"""
IMU & Magnetometer Calibration Utility

This script collects 3D sensor points to calculate:
1. Gyroscope Zero-bias offsets (by computing raw sample mean during a still phase).
2. Magnetometer Hard-iron and Soft-iron correction matrices (by ConvexHull + Least-Squares Ellipsoid Fitting).
Once computed, offsets are sent back to the device to trigger advanced physical calibration!
"""

import json
import argparse
import asyncio
import numpy as np
from scipy.linalg import sqrtm, inv
from scipy.spatial import ConvexHull

from edu_utils import libedu, get_armband_port_name, get_glove_port_name, logger

ACC_COEFFICIENT = 1.0 / 8192.0
GYRO_COEFFICIENT = 1.0 / 16.4
MAG_COEFFICIENT = 1.0 / 65536.0

class IMUMagCalibrator:
    def __init__(self, port: str, baudrate: int = 115200, mock: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.mock = mock
        self.device = None
        self.gyro_offset = [0.0, 0.0, 0.0]
        self.hard_iron = [0.0, 0.0, 0.0]
        self.soft_iron = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        self._raw_gyro_samples = []
        self._raw_mag_samples = []
        self._active_acc_coef = ACC_COEFFICIENT
        self._active_gyro_coef = GYRO_COEFFICIENT
        self._active_mag_coef = MAG_COEFFICIENT

    def _update_coefficient(self, value, fallback: float) -> float:
        try:
            coefficient = float(value)
        except (TypeError, ValueError):
            return fallback
        return coefficient if coefficient > 0.0 else fallback

    def _on_msg_callback(self, device_id: str, msg_json: str) -> None:
        try:
            data = json.loads(msg_json)
        except Exception:
            return

        sensor = data.get("Sensor2App") or data.get("sensor2App") or data.get("sensor_2_app")
        if not sensor:
            return

        imu_resp = sensor.get("imuResp") or sensor.get("imu_resp")
        if imu_resp:
            acc_coef = imu_resp.get("accCoefficient") or imu_resp.get("acc_coefficient")
            gyro_coef = imu_resp.get("gyroCoefficient") or imu_resp.get("gyro_coefficient")
            self._active_acc_coef = self._update_coefficient(acc_coef, self._active_acc_coef)
            self._active_gyro_coef = self._update_coefficient(gyro_coef, self._active_gyro_coef)

        mag_resp = sensor.get("magResp") or sensor.get("mag_resp")
        if mag_resp:
            mag_coef = mag_resp.get("magCoefficient") or mag_resp.get("mag_coefficient")
            self._active_mag_coef = self._update_coefficient(mag_coef, self._active_mag_coef)

    def _on_raw_imu_data(self, data: list[list[float]]) -> None:
        for row in data:
            if len(row) < 7:
                continue
            gyro_coef = self._active_gyro_coef or GYRO_COEFFICIENT
            gyro = [
                int(round(row[4] / gyro_coef)),
                int(round(row[5] / gyro_coef)),
                int(round(row[6] / gyro_coef)),
            ]
            if all(v != -32768 for v in gyro):
                self._raw_gyro_samples.append(gyro)

    def _on_raw_mag_data(self, data: list[list[float]]) -> None:
        for row in data:
            if len(row) >= 4:
                mag_coef = self._active_mag_coef or MAG_COEFFICIENT
                self._raw_mag_samples.append([
                    int(round(row[1] / mag_coef)),
                    int(round(row[2] / mag_coef)),
                    int(round(row[3] / mag_coef)),
                ])

    async def connect(self):
        if self.mock:
            logger.info("⚡ [MOCK] Connected successfully to virtual armband device")
            return
        
        logger.info(f"📡 Connecting to device on port {self.port}...")
        self.device = libedu.EduDevice(self.port, self.baudrate)
        libedu.set_msg_resp_callback(self._on_msg_callback)
        libedu.set_imu_data_callback(self._on_raw_imu_data)
        libedu.set_mag_data_callback(self._on_raw_mag_data)
        await self.device.open_serial_stream(libedu.MessageParser("CALIBRATOR", libedu.MsgType.Edu))
        await asyncio.sleep(0.5)
        
        # Configure raw data uploads for calibration calculation
        await self.device.set_imu_config(libedu.ImuSampleRate.IMU_SR_100, libedu.UploadDataType.RAW_DATA)
        await asyncio.sleep(0.3)
        await self.device.set_mag_config(libedu.MagSampleRate.MAG_SR_20, libedu.UploadDataType.RAW_DATA)
        await asyncio.sleep(0.3)
        
        await self.device.start_sensor_data_stream()
        logger.info(
            "Active scale coefficients: acc=%.9f g/LSB, gyro=%.9f dps/LSB, mag=%.9f Gauss/LSB",
            self._active_acc_coef,
            self._active_gyro_coef,
            self._active_mag_coef,
        )
        logger.info("✓ Data stream started")

    async def calibrate_gyro(self):
        logger.info("🎯 STARTING GYRO ZERO-BIAS CALIBRATION")
        logger.info("⚠️  Please keep the device PERFECTLY STILL on a flat surface...")
        
        still_seconds = 5
        gyro_samples = []
        start_index = len(self._raw_gyro_samples)
        
        for i in range(1, still_seconds + 1):
            await asyncio.sleep(1.0)
            if self.mock:
                # Mock raw still data with minor noise + zero drift
                mock_samples = np.random.normal([2.5, -1.8, 0.9], 0.1, (100, 3))
                gyro_samples.extend(mock_samples)
                logger.info(f"  [{i}/{still_seconds}] virtual gyro samples gathered: {len(gyro_samples)}")
            else:
                gyro_samples = list(self._raw_gyro_samples[start_index:])
                logger.info(f"  [{i}/{still_seconds}] gyro samples gathered: {len(gyro_samples)}")
        
        if len(gyro_samples) < 50:
            logger.error("❌ Calibration failed: not enough samples collected!")
            return False

        # Compute average offsets
        gyro_samples = np.array(gyro_samples)
        self.gyro_offset = np.mean(gyro_samples, axis=0).tolist()
        
        logger.info(f"✅ Gyro offsets computed: X={self.gyro_offset[0]:.4f}, Y={self.gyro_offset[1]:.4f}, Z={self.gyro_offset[2]:.4f}")
        
        if not self.mock:
            # Send gyro offsets to device
            logger.info("📡 Uploading gyro offset parameters to device...")
            await self.device.set_imu_calibration_config(
                libedu.ImuSampleRate.IMU_SR_100,
                libedu.UploadDataType.CALIBRATED_DATA,
                None, # keep acceleration offset default
                self.gyro_offset
            )
            logger.info("✓ Gyro correction uploaded successfully!")
        return True

    def fit_ellipsoid(self, xx, yy, zz):
        """Least-squares ellipsoid fitting."""
        x = xx[:, np.newaxis]
        y = yy[:, np.newaxis]
        z = zz[:, np.newaxis]

        J = np.hstack((x * x, y * y, z * z, x * y, x * z, y * z, x, y, z))
        K = np.ones_like(x)

        JT = J.T
        ABC = inv(JT.dot(J)).dot(JT.dot(K))
        coef = np.append(ABC.flatten(), -1)

        if coef[0] < 0:
            coef = -coef
        return coef

    async def calibrate_mag(self):
        logger.info("🎯 STARTING MAGNETOMETER SOFT/HARD-IRON ELLIPSOID CALIBRATION")
        logger.info("🔄 Please rotate the device slowly in a figure-8 motion for 8 seconds...")
        
        rotate_seconds = 8
        mag_samples = []
        start_index = len(self._raw_mag_samples)
        
        for i in range(1, rotate_seconds + 1):
            await asyncio.sleep(1.0)
            if self.mock:
                # Mock a slightly shifted and squeezed ellipsoid in 3D
                theta = np.random.uniform(0, 2*np.pi, 50)
                phi = np.random.uniform(0, np.pi, 50)
                x = 25.0 + 35.0 * np.sin(phi) * np.cos(theta) + np.random.normal(0, 0.5, 50)
                y = -18.0 + 20.0 * np.sin(phi) * np.sin(theta) + np.random.normal(0, 0.5, 50)
                z = 40.0 + 50.0 * np.cos(phi) + np.random.normal(0, 0.5, 50)
                samples = np.stack((x, y, z), axis=-1)
                mag_samples.extend(samples)
                logger.info(f"  [{i}/{rotate_seconds}] virtual mag samples gathered: {len(mag_samples)}")
            else:
                mag_samples = list(self._raw_mag_samples[start_index:])
                logger.info(f"  [{i}/{rotate_seconds}] mag samples gathered: {len(mag_samples)}")

        if len(mag_samples) < 150:
            logger.error("❌ Calibration failed: not enough samples collected! (requires >= 150)")
            return False

        # Start ellipsoid fitting
        mag_samples = np.array(mag_samples)
        
        # Filter outer boundary points using ConvexHull for precision
        try:
            hull = ConvexHull(mag_samples)
            hull_pts = mag_samples[hull.vertices].T
            x_pts, y_pts, z_pts = hull_pts[0], hull_pts[1], hull_pts[2]
        except Exception:
            x_pts, y_pts, z_pts = mag_samples[:, 0], mag_samples[:, 1], mag_samples[:, 2]

        coef = self.fit_ellipsoid(x_pts, y_pts, z_pts)
        
        a, b, c, d, e, f, g, h, i, j = coef
        d /= 2; e /= 2; f /= 2; g /= 2; h /= 2; i /= 2
        Q = np.array([[a, d, e], [d, b, f], [e, f, c]])
        U = np.array([[g], [h], [i]])
        
        # 1. Compute hard-iron offset
        offset_vector = -inv(Q).dot(U)
        self.hard_iron = offset_vector.flatten().tolist()
        
        # 2. Compute soft-iron correction matrix (assume typical Earth field strength of 50.0 uT)
        Hm = 50.0
        Q_sqrt = sqrtm(Q)
        BtQB = offset_vector.T.dot(Q).dot(offset_vector)
        soft_iron_matrix = Hm * Q_sqrt / sqrtm(BtQB - j)
        self.soft_iron = soft_iron_matrix.tolist()

        logger.info(f"✅ Mag calibration computed:")
        logger.info(f"   Hard-Iron offset (3D): X={self.hard_iron[0]:.4f}, Y={self.hard_iron[1]:.4f}, Z={self.hard_iron[2]:.4f}")
        logger.info(f"   Soft-Iron correction matrix (3x3):")
        for row_idx in range(3):
            logger.info(f"     [ {self.soft_iron[row_idx][0]:.4f}  {self.soft_iron[row_idx][1]:.4f}  {self.soft_iron[row_idx][2]:.4f} ]")
        
        if not self.mock:
            # Upload mag correction params to hardware device
            logger.info("📡 Uploading MAG calibration parameters to device...")
            await self.device.set_mag_calibration_config(
                libedu.MagSampleRate.MAG_SR_20,
                libedu.UploadDataType.CALIBRATED_DATA,
                self.hard_iron,
                self.soft_iron
            )
            logger.info("✓ Mag correction uploaded successfully!")
        return True

    async def disconnect(self):
        if self.mock:
            return
        if self.device:
            await self.device.stop_stream()
            libedu.set_msg_resp_callback(None)
            libedu.set_imu_data_callback(None)
            libedu.set_mag_data_callback(None)
            self.device = None
            logger.info("📡 Disconnected from device")

async def main():
    parser = argparse.ArgumentParser(description="Advanced IMU Zero-bias & Mag Ellipsoid Calibrator")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic calibration simulation")
    parser.add_argument("--device", choices=("armband", "glove"), default="armband", help="Device type to auto-detect")
    parser.add_argument("--imu-only", action="store_true", help="Only run gyroscope zero-bias calibration")
    args = parser.parse_args()

    port = get_glove_port_name() if args.device == "glove" else get_armband_port_name()
    if not port and not args.mock:
        raise RuntimeError(f"No {args.device} device found")
        
    calibrator = IMUMagCalibrator(port, mock=args.mock)
    
    try:
        await calibrator.connect()
        # 1. Calibrate Gyro零偏
        gyro_ok = await calibrator.calibrate_gyro()
        if not gyro_ok: return

        if args.imu_only:
            logger.info("\n🎉 IMU GYRO CALIBRATION COMPLETED!")
            return
        
        await asyncio.sleep(1.0)
        
        # 2. Calibrate Mag软硬铁
        mag_ok = await calibrator.calibrate_mag()
        if not mag_ok: return
        
        logger.info("\n🎉 CONGRATULATIONS! ALL IMU SENSORS ARE FULLY CALIBRATED!")
    finally:
        await calibrator.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
