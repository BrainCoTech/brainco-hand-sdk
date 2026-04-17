"""Mock VisionTouch Device for Testing

Simulates VisionTouch sensor data without requiring actual hardware.
Useful for development, testing, and demonstrations.
"""

import time
import numpy as np
from enum import Enum
from typing import Dict, Any, Optional


class MockVTSDataType(Enum):
    """Mock data types matching pyvitaisdk.VTSDataType"""
    TIME_STAMP = "TIME_STAMP"
    CALIBRATE_IMG = "CALIBRATE_IMG"
    RAW_IMG = "RAW_IMG"
    WARPED_IMG = "WARPED_IMG"
    DIFF_IMG = "DIFF_IMG"
    DEPTH_MAP = "DEPTH_MAP"
    MARKER_IMG = "MARKER_IMG"
    MARKER_ORIGIN_VECTOR = "MARKER_ORIGIN_VECTOR"
    MARKER_CURRENT_VECTOR = "MARKER_CURRENT_VECTOR"
    MARKER_OFFSET_VECTOR = "MARKER_OFFSET_VECTOR"
    XYZ_VECTOR = "XYZ_VECTOR"
    FORCE6D_VECTOR = "FORCE6D_VECTOR"
    SLIP_STATE = "SLIP_STATE"


class MockVTSensorType(Enum):
    """Mock sensor types matching pyvitaisdk.VTSensorType"""
    GF225 = "GF225"
    GF515I = "GF515I"
    GF515T = "GF515T"
    GFBCI = "GFBCI"
    GFBCT = "GFBCT"


class MockSlipState(Enum):
    """Mock slip state"""
    NO_OBJ = "NO_OBJ"                  # 无物体接触
    CONTACT = "CONTACT"                # 初次接触
    STEADY_HOLD = "STEADY_HOLD"        # 稳定保持
    INCIPIENT_SLIP = "INCIPIENT_SLIP"  # 初始滑移
    PARTIAL_SLIP = "PARTIAL_SLIP"      # 部分滑移
    COMPLETE_SLIP = "COMPLETE_SLIP"    # 完全滑移


class MockVTSensor:
    """Mock VisionTouch sensor
    
    Generates synthetic data that mimics real VisionTouch sensor output.
    """
    
    def __init__(self, config=None, sensor_type=None, marker_size=21):
        """Initialize mock sensor
        
        Args:
            config: Ignored (for compatibility)
            sensor_type: Ignored (for compatibility)
            marker_size: Marker grid size (default: 21x21)
        """
        self.marker_size = marker_size
        self.calibrated = False
        self.start_time = time.time()
        
        # Simulation parameters
        self.image_size = (480, 640, 3)  # H, W, C
        self.marker_grid = (9, 9)  # N, M
        
        # Animation state
        self.phase = 0.0
        self.slip_counter = 0
        
        print(f"[Mock] VTSensor initialized (marker_size={marker_size})")
        
    def calibrate(self, calib_image=None):
        """Mock calibration"""
        self.calibrated = True
        print("[Mock] Sensor calibrated")
        
    def collect_sensor_data(self, *data_types) -> Dict[Any, Any]:
        """Collect mock sensor data
        
        Args:
            *data_types: Requested data types (MockVTSDataType)
            
        Returns:
            Dictionary mapping data types to generated data
        """
        if not self.calibrated:
            raise RuntimeError("Sensor not calibrated. Call calibrate() first.")
        
        # Update animation phase
        self.phase += 0.1
        self.slip_counter += 1
        
        data = {}
        
        for dtype in data_types:
            if dtype == MockVTSDataType.TIME_STAMP:
                data[dtype] = int((time.time() - self.start_time) * 1000)
                
            elif dtype == MockVTSDataType.CALIBRATE_IMG:
                data[dtype] = self._generate_calibrate_image()
                
            elif dtype == MockVTSDataType.RAW_IMG:
                data[dtype] = self._generate_raw_image()
                
            elif dtype == MockVTSDataType.WARPED_IMG:
                data[dtype] = self._generate_warped_image()
                
            elif dtype == MockVTSDataType.DIFF_IMG:
                data[dtype] = self._generate_diff_image()
                
            elif dtype == MockVTSDataType.DEPTH_MAP:
                data[dtype] = self._generate_depth_map()
                
            elif dtype == MockVTSDataType.MARKER_IMG:
                data[dtype] = self._generate_marker_image()
                
            elif dtype == MockVTSDataType.MARKER_ORIGIN_VECTOR:
                data[dtype] = self._generate_marker_origin()
                
            elif dtype == MockVTSDataType.MARKER_CURRENT_VECTOR:
                data[dtype] = self._generate_marker_current()
                
            elif dtype == MockVTSDataType.MARKER_OFFSET_VECTOR:
                data[dtype] = self._generate_marker_offset()
                
            elif dtype == MockVTSDataType.XYZ_VECTOR:
                data[dtype] = self._generate_xyz_vector()
                
            elif dtype == MockVTSDataType.FORCE6D_VECTOR:
                data[dtype] = self._generate_force6d()
                
            elif dtype == MockVTSDataType.SLIP_STATE:
                data[dtype] = self._generate_slip_state()
        
        return data
    
    def _generate_calibrate_image(self) -> np.ndarray:
        """Generate synthetic calibrate image"""
        h, w, c = self.image_size
        img = np.ones((h, w, c), dtype=np.uint8) * 100
        # Add some mock calibration pattern
        import cv2
        cv2.putText(img, "MOCK CALIBRATION", (40, h//2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200, 200, 200), 2)
        return img
        
    def _generate_raw_image(self) -> np.ndarray:
        """Generate synthetic raw image (distorted)"""
        # Just use warped image but slightly darker to simulate raw
        img = self._generate_warped_image()
        return (img * 0.8).astype(np.uint8)
    
    def _generate_warped_image(self) -> np.ndarray:
        """Generate synthetic warped image"""
        h, w, c = self.image_size
        
        # Create gradient background
        y, x = np.ogrid[:h, :w]
        
        img = np.zeros((h, w, c), dtype=np.uint8)
        
        # Fast vectorized numpy math instead of double for-loop (which blocked the GIL)
        img[:, :, 0] = (128 + 50 * np.sin(y / 20.0 + self.phase)).astype(np.uint8)
        img[:, :, 1] = (128 + 50 * np.sin(x / 20.0 + self.phase)).astype(np.uint8)
        img[:, :, 2] = (128 + 50 * np.cos((y + x) / 30.0 + self.phase)).astype(np.uint8)
        
        # Add circular "contact" region
        center_y, center_x = h // 2, w // 2
        radius = 100 + 30 * np.sin(self.phase)
        
        mask = (x - center_x)**2 + (y - center_y)**2 <= radius**2
        img[mask] = (img[mask] * 0.7 + 50).astype(np.uint8)
        
        return img
    
    def _generate_diff_image(self) -> np.ndarray:
        """Generate synthetic diff image"""
        h, w, c = self.image_size
        
        # Create diff image (difference from background)
        img = np.zeros((h, w, c), dtype=np.uint8)
        
        # Add contact region
        center_y, center_x = h // 2, w // 2
        radius = 100 + 30 * np.sin(self.phase)
        
        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        mask = dist <= radius
        
        # Intensity based on distance from center
        intensity = np.clip(255 * (1 - dist / radius), 0, 255).astype(np.uint8)
        img[mask, 0] = intensity[mask]
        img[mask, 1] = intensity[mask] // 2
        img[mask, 2] = intensity[mask] // 2
        
        return img
    
    def _generate_depth_map(self) -> np.ndarray:
        """Generate synthetic depth map"""
        h, w, _ = self.image_size
        
        # Create depth map (float32)
        depth = np.zeros((h, w), dtype=np.float32)
        
        # Add Gaussian-like contact region
        center_y, center_x = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        
        # Distance from center
        dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        
        # Gaussian depth profile
        sigma = 80 + 20 * np.sin(self.phase)
        max_depth = 2.5 + 0.5 * np.sin(self.phase * 0.5)
        depth = max_depth * np.exp(-(dist**2) / (2 * sigma**2))
        
        # Add some noise
        depth += np.random.normal(0, 0.05, depth.shape)
        depth = np.clip(depth, 0, None)
        
        return depth
    
    def _generate_marker_image(self) -> np.ndarray:
        """Generate synthetic marker image"""
        img = self._generate_warped_image()
        
        # Draw marker grid
        n, m = self.marker_grid
        h, w, _ = self.image_size
        
        for i in range(n):
            for j in range(m):
                y = int(h * (i + 1) / (n + 1))
                x = int(w * (j + 1) / (m + 1))
                
                # Draw marker (small circle)
                import cv2
                cv2.circle(img, (x, y), 3, (0, 255, 0), -1)
        
        return img
    
    def _generate_marker_origin(self) -> np.ndarray:
        """Generate marker origin positions"""
        n, m = self.marker_grid
        h, w, _ = self.image_size
        
        origin = np.zeros((n, m, 2), dtype=np.float32)
        
        for i in range(n):
            for j in range(m):
                origin[i, j, 0] = w * (j + 1) / (m + 1)  # x
                origin[i, j, 1] = h * (i + 1) / (n + 1)  # y
        
        return origin
    
    def _generate_marker_current(self) -> np.ndarray:
        """Generate current marker positions (with offset)"""
        origin = self._generate_marker_origin()
        offset = self._generate_marker_offset()
        return origin + offset
    
    def _generate_marker_offset(self) -> np.ndarray:
        """Generate marker offset vectors"""
        n, m = self.marker_grid
        
        offset = np.zeros((n, m, 2), dtype=np.float32)
        
        # Add wave-like offset pattern
        for i in range(n):
            for j in range(m):
                offset[i, j, 0] = 5 * np.sin(i / 2 + self.phase)  # x offset
                offset[i, j, 1] = 5 * np.cos(j / 2 + self.phase)  # y offset
        
        return offset
    
    def _generate_xyz_vector(self) -> np.ndarray:
        """Generate XYZ displacement vectors"""
        n, m = self.marker_grid
        
        xyz = np.zeros((n, m, 3), dtype=np.float32)
        
        # Generate 3D positions
        for i in range(n):
            for j in range(m):
                # X, Y based on grid position
                xyz[i, j, 0] = (j - m / 2) * 10
                xyz[i, j, 1] = (i - n / 2) * 10
                
                # Z (depth) with Gaussian profile
                dist = np.sqrt((i - n/2)**2 + (j - m/2)**2)
                xyz[i, j, 2] = 2.0 * np.exp(-(dist**2) / 20) * (1 + 0.2 * np.sin(self.phase))
        
        return xyz
    
    def _generate_force6d(self) -> np.ndarray:
        """Generate 6D force/torque vector"""
        # [Fx, Fy, Fz, Mx, My, Mz]
        force6d = np.zeros(6, dtype=np.float32)
        
        # Simulate varying forces
        force6d[0] = 2.0 * np.sin(self.phase)           # Fx
        force6d[1] = 1.5 * np.cos(self.phase * 1.2)     # Fy
        force6d[2] = 5.0 + 2.0 * np.sin(self.phase * 0.5)  # Fz (normal force)
        force6d[3] = 0.01 * np.sin(self.phase * 0.8)    # Mx
        force6d[4] = 0.015 * np.cos(self.phase * 0.6)   # My
        force6d[5] = 0.005 * np.sin(self.phase * 1.5)   # Mz
        
        # Add small noise
        force6d += np.random.normal(0, 0.1, 6)
        
        return force6d
    
    def _generate_slip_state(self):
        """Generate slip state"""
        # Simulate different slip states
        cycle = self.slip_counter % 200
        if cycle < 80:
            return MockSlipState.NO_OBJ
        elif cycle < 90:
            return MockSlipState.CONTACT
        elif cycle < 150:
            return MockSlipState.STEADY_HOLD
        elif cycle < 160:
            return MockSlipState.INCIPIENT_SLIP
        elif cycle < 180:
            return MockSlipState.PARTIAL_SLIP
        else:
            return MockSlipState.COMPLETE_SLIP
    
    def release(self):
        """Release mock sensor"""
        print("[Mock] Sensor released")


class MockVTSDeviceFinder:
    """Mock device finder"""
    
    def __init__(self):
        self.mock_devices = ["MockVTS_Left_001", "MockVTS_Right_002"]
        print("[Mock] Device finder initialized")
        
    def get_sns(self):
        """Get list of mock device serial numbers"""
        return self.mock_devices
        
    def get_devices(self):
        """Get list of mock device configs"""
        return [{"sn": sn, "type": "mock"} for sn in self.mock_devices]
        
    def count(self):
        """Get number of available mock devices"""
        return len(self.mock_devices)
        
    def indexes(self):
        """Get list of mock device indexes"""
        return list(range(len(self.mock_devices)))
    
    def get_device_by_sn(self, sn: str):
        """Get mock device config by serial number"""
        if sn in self.mock_devices:
            return {"sn": sn, "type": "mock"}
        return None


class MockVTSError(Exception):
    """Mock VTS error"""
    def __init__(self, message, suggestion="Check mock device configuration"):
        super().__init__(message)
        self.suggestion = suggestion


# Export mock classes with same names as real SDK
VTSensor = MockVTSensor
VTSensorType = MockVTSensorType
VTSDeviceFinder = MockVTSDeviceFinder
VTSDataType = MockVTSDataType
VTSError = MockVTSError
SlipState = MockSlipState


def is_mock_mode():
    """Check if running in mock mode"""
    return True


if __name__ == "__main__":
    """Test mock device"""
    print("Testing Mock VisionTouch Device\n")
    
    # Find device
    finder = MockVTSDeviceFinder()
    sns = finder.get_sns()
    print(f"Found devices: {sns}\n")
    
    # Create sensor
    config = finder.get_device_by_sn(sns[0])
    sensor = MockVTSensor(config=config)
    sensor.calibrate()
    
    # Collect data
    print("\nCollecting data...")
    for i in range(5):
        data = sensor.collect_sensor_data(
            MockVTSDataType.FORCE6D_VECTOR,
            MockVTSDataType.DEPTH_MAP,
            MockVTSDataType.SLIP_STATE,
        )
        
        force6d = data[MockVTSDataType.FORCE6D_VECTOR]
        depth_map = data[MockVTSDataType.DEPTH_MAP]
        slip_state = data[MockVTSDataType.SLIP_STATE]
        
        print(f"\nFrame {i+1}:")
        print(f"  Force6D: Fx={force6d[0]:.2f}, Fy={force6d[1]:.2f}, Fz={force6d[2]:.2f}")
        print(f"  Depth: min={depth_map.min():.2f}, max={depth_map.max():.2f}, mean={depth_map.mean():.2f}")
        print(f"  Slip: {slip_state.name}")
        
        time.sleep(0.1)
    
    sensor.release()
    print("\n✅ Mock device test completed!")
