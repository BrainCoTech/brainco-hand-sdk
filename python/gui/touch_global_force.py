"""Global Force Calculator for Revo1 Touch

Calculates global 6D force/torque from Revo1 Touch's 13 local 3D force sensors.
"""

import numpy as np
from typing import Optional
from common_imports import logger


# Sensor positions on hand (approximate, in mm)
# Coordinate system: X=forward, Y=left, Z=up (right hand)
SENSOR_POSITIONS = {
    # Thumb (2 sensors)
    'thumb': [
        np.array([50.0, 40.0, 10.0]),   # Sensor 1
        np.array([55.0, 42.0, 8.0]),    # Sensor 2
    ],
    # Index (3 sensors)
    'index': [
        np.array([80.0, 20.0, 12.0]),   # Sensor 1
        np.array([85.0, 20.0, 10.0]),   # Sensor 2
        np.array([90.0, 20.0, 8.0]),    # Sensor 3
    ],
    # Middle (3 sensors)
    'middle': [
        np.array([85.0, 0.0, 12.0]),    # Sensor 1
        np.array([90.0, 0.0, 10.0]),    # Sensor 2
        np.array([95.0, 0.0, 8.0]),     # Sensor 3
    ],
    # Ring (3 sensors)
    'ring': [
        np.array([80.0, -20.0, 12.0]),  # Sensor 1
        np.array([85.0, -20.0, 10.0]),  # Sensor 2
        np.array([90.0, -20.0, 8.0]),   # Sensor 3
    ],
    # Pinky (2 sensors)
    'pinky': [
        np.array([70.0, -35.0, 10.0]),  # Sensor 1
        np.array([75.0, -37.0, 8.0]),   # Sensor 2
    ],
}

FINGER_NAMES = ['thumb', 'index', 'middle', 'ring', 'pinky']


class GlobalForceCalculator:
    """Calculate global 6D force from Revo1/Revo2 capacitive touch data
    
    Revo1 Touch: Firmware outputs 13 force groups (Thumb=2, Index/Mid/Ring=3, Pinky=2)
                 Each group has normal_force, tangential_force, tangential_direction
                 → Per-finger 6D force/torque is meaningful
    
    Revo2 Touch: Firmware outputs 5 force groups (1 per finger)
                 Only force1/direction1 are valid, force2/3 are always 0
                 → Per-finger only 3D force (no torque from a single point)
    """
    
    def __init__(self, sensor_positions: Optional[dict] = None, is_revo2: bool = False):
        """
        Args:
            sensor_positions: Custom sensor positions (optional)
                             If None, uses default SENSOR_POSITIONS
            is_revo2: If True, assumes Revo2 Touch (1 sensor per finger)
        """
        self.sensor_positions = sensor_positions or SENSOR_POSITIONS
        self.is_revo2 = is_revo2
    
    def _get_sensor_count(self, finger_idx: int) -> int:
        """Get number of force sensors for a finger
        
        Revo1: Thumb=2, Index/Mid/Ring=3, Pinky=2 (total 13)
        Revo2: All fingers = 1 (total 5)
        """
        if self.is_revo2:
            return 1
        return 2 if finger_idx in [0, 4] else 3
        
    def calculate(self, touch_data) -> np.ndarray:
        """Calculate global 6D force/torque
        
        Args:
            touch_data: TouchFingerData from stark_get_touch_status
            
        Returns:
            np.ndarray: [Fx, Fy, Fz, Mx, My, Mz] in N and N·m
        """
        Fx_total = 0.0
        Fy_total = 0.0
        Fz_total = 0.0
        Mx_total = 0.0
        My_total = 0.0
        Mz_total = 0.0
        
        try:
            for finger_idx, finger in enumerate(touch_data.items):
                finger_name = FINGER_NAMES[finger_idx]
                positions = self.sensor_positions[finger_name]
                
                # Number of sensors per finger (Revo1: 2-3, Revo2: 1)
                num_sensors = self._get_sensor_count(finger_idx)
                
                for sensor_idx in range(num_sensors):
                    # Get force data
                    normal_force = getattr(finger, f'normal_force{sensor_idx+1}', 0) / 100.0  # Convert to N
                    tangential_force = getattr(finger, f'tangential_force{sensor_idx+1}', 0) / 100.0  # Convert to N
                    direction = getattr(finger, f'tangential_direction{sensor_idx+1}', 0xFFFF)  # Degrees
                    
                    # Skip if no valid data
                    if normal_force == 0 and tangential_force == 0:
                        continue
                    
                    # Convert tangential force to XY components
                    if direction != 0xFFFF:  # Direction is valid
                        angle_rad = np.radians(direction)
                        fx_local = tangential_force * np.cos(angle_rad)
                        fy_local = tangential_force * np.sin(angle_rad)
                    else:
                        fx_local = 0.0
                        fy_local = 0.0
                    
                    fz_local = normal_force
                    
                    # Accumulate forces
                    Fx_total += fx_local
                    Fy_total += fy_local
                    Fz_total += fz_local
                    
                    # Calculate torques (τ = r × F)
                    # positions are in mm, convert to meters for N·m torque
                    if sensor_idx < len(positions):
                        pos = positions[sensor_idx] / 1000.0  # mm → m
                        # Torque = position × force
                        Mx_total += pos[1] * fz_local - pos[2] * fy_local
                        My_total += pos[2] * fx_local - pos[0] * fz_local
                        Mz_total += pos[0] * fy_local - pos[1] * fx_local
        
        except Exception as e:
            logger.error(f"Error calculating global force: {e}")
        
        return np.array([Fx_total, Fy_total, Fz_total, Mx_total, My_total, Mz_total])
    
    def calculate_per_finger(self, touch_data) -> dict:
        """Calculate 6D force/torque for each finger independently
        
        Args:
            touch_data: TouchFingerData from stark_get_touch_status
            
        Returns:
            dict: {
                'thumb': [Fx, Fy, Fz, Mx, My, Mz],
                'index': [Fx, Fy, Fz, Mx, My, Mz],
                'middle': [Fx, Fy, Fz, Mx, My, Mz],
                'ring': [Fx, Fy, Fz, Mx, My, Mz],
                'pinky': [Fx, Fy, Fz, Mx, My, Mz],
            }
        """
        per_finger_forces = {}
        
        try:
            for finger_idx, finger in enumerate(touch_data.items):
                finger_name = FINGER_NAMES[finger_idx]
                positions = self.sensor_positions[finger_name]
                
                Fx = 0.0
                Fy = 0.0
                Fz = 0.0
                Mx = 0.0
                My = 0.0
                Mz = 0.0
                
                # Number of sensors per finger (Revo1: 2-3, Revo2: 1)
                num_sensors = self._get_sensor_count(finger_idx)
                
                for sensor_idx in range(num_sensors):
                    # Get force data
                    normal_force = getattr(finger, f'normal_force{sensor_idx+1}', 0) / 100.0
                    tangential_force = getattr(finger, f'tangential_force{sensor_idx+1}', 0) / 100.0
                    direction = getattr(finger, f'tangential_direction{sensor_idx+1}', 0xFFFF)
                    
                    # Skip if no valid data
                    if normal_force == 0 and tangential_force == 0:
                        continue
                    
                    # Convert tangential force to XY components
                    if direction != 0xFFFF:
                        angle_rad = np.radians(direction)
                        fx_local = tangential_force * np.cos(angle_rad)
                        fy_local = tangential_force * np.sin(angle_rad)
                    else:
                        fx_local = 0.0
                        fy_local = 0.0
                    
                    fz_local = normal_force
                    
                    # Accumulate forces for this finger
                    Fx += fx_local
                    Fy += fy_local
                    Fz += fz_local
                    
                    # Calculate torques relative to finger base
                    # positions in mm → convert to m for N·m torque
                    # Note: For Revo2 (single sensor), torque is still computed
                    # but only from 1 point - less meaningful than Revo1
                    if sensor_idx < len(positions):
                        pos = positions[sensor_idx] / 1000.0  # mm → m
                        Mx += pos[1] * fz_local - pos[2] * fy_local
                        My += pos[2] * fx_local - pos[0] * fz_local
                        Mz += pos[0] * fy_local - pos[1] * fx_local
                
                per_finger_forces[finger_name] = np.array([Fx, Fy, Fz, Mx, My, Mz])
        
        except Exception as e:
            logger.error(f"Error calculating per-finger force: {e}")
        
        return per_finger_forces
    
    def calculate_per_sensor(self, touch_data) -> dict:
        """Calculate 3D force for each individual sensor
        
        Args:
            touch_data: TouchFingerData from stark_get_touch_status
            
        Returns:
            dict: {
                'thumb': [[Fx1, Fy1, Fz1], [Fx2, Fy2, Fz2]],
                'index': [[Fx1, Fy1, Fz1], [Fx2, Fy2, Fz2], [Fx3, Fy3, Fz3]],
                ...
            }
        """
        per_sensor_forces = {}
        
        try:
            for finger_idx, finger in enumerate(touch_data.items):
                finger_name = FINGER_NAMES[finger_idx]
                sensor_forces = []
                
                # Number of sensors per finger (Revo1: 2-3, Revo2: 1)
                num_sensors = self._get_sensor_count(finger_idx)
                
                for sensor_idx in range(num_sensors):
                    # Get force data
                    normal_force = getattr(finger, f'normal_force{sensor_idx+1}', 0) / 100.0
                    tangential_force = getattr(finger, f'tangential_force{sensor_idx+1}', 0) / 100.0
                    direction = getattr(finger, f'tangential_direction{sensor_idx+1}', 0xFFFF)
                    
                    # Convert tangential force to XY components
                    if direction != 0xFFFF:
                        angle_rad = np.radians(direction)
                        fx = tangential_force * np.cos(angle_rad)
                        fy = tangential_force * np.sin(angle_rad)
                    else:
                        fx = 0.0
                        fy = 0.0
                    
                    fz = normal_force
                    
                    sensor_forces.append(np.array([fx, fy, fz]))
                
                per_sensor_forces[finger_name] = sensor_forces
        
        except Exception as e:
            logger.error(f"Error calculating per-sensor force: {e}")
        
        return per_sensor_forces
    
    def calculate_summary(self, touch_data) -> dict:
        """Calculate global force and additional summary statistics
        
        Returns:
            dict with keys:
                - force6d: [Fx, Fy, Fz, Mx, My, Mz]
                - total_force: Magnitude of total force
                - total_torque: Magnitude of total torque
                - active_sensors: Number of active sensors
                - max_normal_force: Maximum normal force across all sensors
                - max_tangential_force: Maximum tangential force
        """
        force6d = self.calculate(touch_data)
        
        # Calculate magnitudes
        total_force = np.linalg.norm(force6d[:3])
        total_torque = np.linalg.norm(force6d[3:])
        
        # Count active sensors and find max forces
        active_sensors = 0
        max_normal = 0.0
        max_tangential = 0.0
        
        try:
            for finger_idx, finger in enumerate(touch_data.items):
                num_sensors = self._get_sensor_count(finger_idx)
                
                for sensor_idx in range(num_sensors):
                    normal = getattr(finger, f'normal_force{sensor_idx+1}', 0) / 100.0
                    tangential = getattr(finger, f'tangential_force{sensor_idx+1}', 0) / 100.0
                    
                    if normal > 0.1 or tangential > 0.1:  # Threshold 0.1N
                        active_sensors += 1
                    
                    max_normal = max(max_normal, normal)
                    max_tangential = max(max_tangential, tangential)
        
        except Exception as e:
            logger.error(f"Error calculating summary: {e}")
        
        return {
            'force6d': force6d,
            'total_force': total_force,
            'total_torque': total_torque,
            'active_sensors': active_sensors,
            'max_normal_force': max_normal,
            'max_tangential_force': max_tangential,
        }


if __name__ == "__main__":
    """Test global force calculator"""
    print("Testing Global Force Calculator\n")
    
    # Mock touch data for testing
    class MockFingerItem:
        def __init__(self):
            self.normal_force1 = 500  # 5.0 N
            self.normal_force2 = 300  # 3.0 N
            self.normal_force3 = 200  # 2.0 N
            self.tangential_force1 = 100  # 1.0 N
            self.tangential_force2 = 50   # 0.5 N
            self.tangential_force3 = 30   # 0.3 N
            self.tangential_direction1 = 45   # 45 degrees
            self.tangential_direction2 = 90   # 90 degrees
            self.tangential_direction3 = 135  # 135 degrees
    
    class MockTouchData:
        def __init__(self):
            self.items = [MockFingerItem() for _ in range(5)]
    
    # Test calculation
    calculator = GlobalForceCalculator()
    mock_data = MockTouchData()
    
    # Test 1: Global force
    print("="*60)
    print("Test 1: Global Force/Torque (All Fingers)")
    print("="*60)
    summary = calculator.calculate_summary(mock_data)
    
    print("Global Force/Torque:")
    print(f"  Fx: {summary['force6d'][0]:+.3f} N")
    print(f"  Fy: {summary['force6d'][1]:+.3f} N")
    print(f"  Fz: {summary['force6d'][2]:+.3f} N")
    print(f"  Mx: {summary['force6d'][3]:+.3f} N·m")
    print(f"  My: {summary['force6d'][4]:+.3f} N·m")
    print(f"  Mz: {summary['force6d'][5]:+.3f} N·m")
    print(f"\nTotal Force: {summary['total_force']:.3f} N")
    print(f"Total Torque: {summary['total_torque']:.3f} N·m")
    print(f"Active Sensors: {summary['active_sensors']}/13")
    print(f"Max Normal Force: {summary['max_normal_force']:.2f} N")
    print(f"Max Tangential Force: {summary['max_tangential_force']:.2f} N")
    
    # Test 2: Per-finger force
    print("\n" + "="*60)
    print("Test 2: Per-Finger Force/Torque")
    print("="*60)
    per_finger = calculator.calculate_per_finger(mock_data)
    
    for finger_name, force6d in per_finger.items():
        print(f"\n{finger_name.capitalize()}:")
        print(f"  Force:  Fx={force6d[0]:+.2f}, Fy={force6d[1]:+.2f}, Fz={force6d[2]:+.2f} N")
        print(f"  Torque: Mx={force6d[3]:+.3f}, My={force6d[4]:+.3f}, Mz={force6d[5]:+.3f} N·m")
        total = np.linalg.norm(force6d[:3])
        print(f"  Total Force: {total:.2f} N")
    
    # Test 3: Per-sensor force
    print("\n" + "="*60)
    print("Test 3: Per-Sensor 3D Force")
    print("="*60)
    per_sensor = calculator.calculate_per_sensor(mock_data)
    
    for finger_name, sensor_forces in per_sensor.items():
        print(f"\n{finger_name.capitalize()} ({len(sensor_forces)} sensors):")
        for i, force3d in enumerate(sensor_forces, 1):
            print(f"  Sensor {i}: Fx={force3d[0]:+.2f}, Fy={force3d[1]:+.2f}, Fz={force3d[2]:+.2f} N")
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)
