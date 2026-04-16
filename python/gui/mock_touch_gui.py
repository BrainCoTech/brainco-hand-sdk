import sys
import numpy as np
import time
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PySide6.QtCore import QTimer
import math

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.touch_panel_force import ForceTouchSubPanel
from gui.touch_panel_pressure import PressureTouchSubPanel
from gui.touch_panel_revo3 import V3TouchSubPanel

class MockDataGenerator:
    def __init__(self):
        self.t = 0.0

    def get_force_data(self):
        """Mock Fx, Fy, Fz, Mx, My for 5 fingers. (25 values scaled * 100)"""
        data = []
        for i in range(5):
            phase = self.t + i * 1.5
            # Fx, Fy simulate rubbing back and forth
            fx = int(math.sin(phase) * 15 * 100) & 0xFFFF
            fy = int(math.cos(phase) * 15 * 100) & 0xFFFF
            # Fz simulate pressing down periodically
            fz = int((math.sin(phase * 0.5) * 15 + 15) * 100) & 0xFFFF
            # Torque
            mx = int(math.sin(phase * 2) * 0.03 * 100) & 0xFFFF
            my = int(math.cos(phase * 2) * 0.03 * 100) & 0xFFFF
            data.extend([fx, fy, fz, mx, my])
        return data
        
    def get_pressure_data(self):
        """Mock pressure data. 6 components for summary, and details."""
        # 6 elements summary
        summary = [int(math.sin(self.t + i) * 15 + 15) & 0xFFFF for i in range(6)]
        
        # Details needs to be objects with `.sensors` property
        class DummyDetail:
            def __init__(self, sensors):
                self.sensors = sensors
        
        details = []
        # 5 fingers (9 points)
        for i in range(5):
            sensors = [int(math.sin(self.t + j * 0.5 + i) * 10 + 10) & 0xFFFF for j in range(9)]
            details.append(DummyDetail(sensors))
            
        # Palm (46 points)
        palm_sensors = [int(math.sin(self.t * 0.5 + j * 0.2) * 15 + 15) & 0xFFFF for j in range(46)]
        details.append(DummyDetail(palm_sensors))
        
        return summary, details

    def get_v3_data(self):
        """Mock V3 Touch Data: 16 summary, 11 modules array"""
        class DummyV3Data:
            def __init__(self, summary, modules):
                self.summary = summary
                self.modules = modules
                
        summary = [int(math.sin(self.t + i*0.2) * 20 + 20) & 0xFFFF for i in range(16)]
        
        # Module point counts:
        counts = [29, 22, 44, 21, 29, 21, 29, 21, 29, 21, 29]
        modules = []
        for c in counts:
            pts = [int(math.sin(self.t*2 + x*0.1) * 30 + 30) & 0xFFFF for x in range(c)]
            modules.append(pts)
            
        return DummyV3Data(summary, modules)


class MockWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Touch Sensor Mock Visualizer")
        self.resize(1000, 700)
        
        self.tabs = QTabWidget()
        
        # 1. ArrayPressure (Force)
        self.force_panel = ForceTouchSubPanel()
        self.tabs.addTab(self.force_panel, "Revo2: ArrayPressure (3D Force)")
        
        # 2. Pressure
        self.pressure_panel = PressureTouchSubPanel()
        self.tabs.addTab(self.pressure_panel, "Revo2: Pressure Arrays")
        
        # 3. V3 Touch (High-Res Arrays)
        self.v3_panel = V3TouchSubPanel()
        self.tabs.addTab(self.v3_panel, "Revo3: V3 Touch (High-Res)")
        
        self.setCentralWidget(self.tabs)
        
        self.mock_gen = MockDataGenerator()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(50)  # 20hz

    def update_data(self):
        self.mock_gen.t += 0.05
        
        # 1. Update Force/Torque (ArrayPressure)
        force_raw = self.mock_gen.get_force_data()
        self.force_panel.update_data(force_raw)
        
        # 2. Update Pressure
        summ, det = self.mock_gen.get_pressure_data()
        self.pressure_panel.update_summary(summ)
        self.pressure_panel.update_detail(det)
        
        # 3. Update V3
        v3_obj = self.mock_gen.get_v3_data()
        self.v3_panel.update_data(v3_obj)

if __name__ == "__main__":
    import signal
    # Make Python's signal handler immediately kill the process on Ctrl+C,
    # instead of throwing KeyboardInterrupt inside a running Qt event loop (QTimer).
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    window = MockWindow()
    window.show()
    sys.exit(app.exec())
