"""Mock Device for GUI Debugging"""

import asyncio
import time
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

class MockDeviceInfo:
    def __init__(self, hw_type):
        self.hardware_type = hw_type
        self.sku_type = 0 # MediumRight
        self.serial_number = "MOCK-12345678"
        self.firmware_version = "9.9.9"
        
    def is_touch(self):
        from common_imports import sdk
        return self.hardware_type in [
            sdk.StarkHardwareType.Revo1Touch,
            sdk.StarkHardwareType.Revo1AdvancedTouch,
            sdk.StarkHardwareType.Revo2Touch,
            sdk.StarkHardwareType.Revo2TouchPressure,
            sdk.StarkHardwareType.Revo2TouchForce3D,
            sdk.StarkHardwareType.Revo2TouchArrayPressure,
        ]
        
    def uses_revo1_motor_api(self):
        from common_imports import sdk
        return self.hardware_type in [
            sdk.StarkHardwareType.Revo1Protobuf,
            sdk.StarkHardwareType.Revo1Basic,
            sdk.StarkHardwareType.Revo1Touch,
        ]
        
    def uses_revo2_motor_api(self):
        return not self.uses_revo1_motor_api()

class MockMotorStatusData:
    def __init__(self):
        self.positions = [0] * 6
        self.speeds = [0] * 6
        self.currents = [0] * 6
        self.states = [0] * 6

class MockDeviceContext:
    """Mock Device Context matching PyDeviceContext interface"""
    
    def __init__(self, hw_type):
        self.hw_type = hw_type
        self.is_mock = True
        self.start_time = time.time()
    
    async def get_device_info(self, slave_id):
        return MockDeviceInfo(self.hw_type)
        
    async def get_turbo_mode_enabled(self, slave_id):
        return False
        
    async def get_turbo_config(self, slave_id):
        from common_imports import sdk
        class MockTurboConfig:
            def __init__(self):
                self.interval = 10
                self.duration = 1000
        return MockTurboConfig()
        
    async def get_auto_calibration_enabled(self, slave_id):
        return True
        
    async def get_led_enabled(self, slave_id):
        return True
        
    async def get_buzzer_enabled(self, slave_id):
        return True
        
    async def get_vibration_enabled(self, slave_id):
        return True
        
    async def get_all_finger_settings(self, slave_id):
        from common_imports import sdk
        class MockFingerSettings:
            def __init__(self):
                self.min_position = 0.0
                self.max_position = 100.0
                self.max_speed = 50.0
                self.max_current = 500.0
        return [MockFingerSettings() for _ in range(6)]
        
    async def get_finger_protected_currents(self, slave_id):
        return [1000 for _ in range(6)]
        
    async def get_global_protect_current(self, slave_id):
        return 1500
        
    def uses_pressure_touch_api(self, slave_id):
        return self.hw_type in [sdk.StarkHardwareType.Revo2TouchPressure, 
                                sdk.StarkHardwareType.Revo2TouchForce3D, 
                                sdk.StarkHardwareType.Revo2TouchArrayPressure]
                                
    def get_protocol_type(self):
        from common_imports import sdk
        return sdk.StarkProtocolType.Modbus
        
    async def close(self):
        pass
        
    # Catch-all for other async methods to avoid crashing
    def __getattr__(self, name):
        async def mock_method(*args, **kwargs):
            # print(f"[MockDevice] Called {name}({args}, {kwargs})")
            pass
        return mock_method
