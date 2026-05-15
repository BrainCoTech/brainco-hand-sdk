"""VisionTouch Independent Window

Displays VisionTouch sensor data in a separate window.
Can be launched from main window's Tools menu.

Features:
- 6D Force/Torque visualization
- Depth map heatmap
- Raw image display (Warped, Diff, Marker)
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QStatusBar,
    QGroupBox, QGridLayout, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QImage, QPixmap

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import real SDK, fall back to mock
MOCK_MODE = False
try:
    from pyvitaisdk import VTSensor, VTSDeviceFinder, VTSDataType, VTSError, VTSensorType
    HAS_VITAI_SDK = True
    print("✅ Using real pyvitaisdk")
except ImportError:
    HAS_VITAI_SDK = False
    try:
        from .vision_touch_mock import (
            VTSensor, VTSDeviceFinder, VTSDataType, VTSError, VTSensorType
        )
        MOCK_MODE = True
        print("⚠ pyvitaisdk not found, using Mock Device")
        print("Install real SDK with: pip install pyvitaisdk")
    except ImportError:
        print("❌ Error: Neither real nor mock VisionTouch available")
        VTSensor = None
        VTSDeviceFinder = None

from .touch_common import logger, COLORS
from .i18n import tr


class VisionTouchSignals(QObject):
    """Signals for thread-safe GUI updates"""
    force_data_ready = Signal(np.ndarray)  # 6D force vector
    depth_data_ready = Signal(np.ndarray)  # Depth map
    image_data_ready = Signal(dict)  # Images dict
    slip_data_ready = Signal(object, object)  # (slip_state, image)
    xyz_data_ready = Signal(np.ndarray)  # XYZ vector
    marker_data_ready = Signal(np.ndarray, np.ndarray, np.ndarray, object)  # (origin, current, offset, image)
    status_message = Signal(str)  # Status message
    error_occurred = Signal(str)  # Error message


class VisionTouchDataCollector:
    """Background thread for VisionTouch data collection"""
    
    def __init__(self, vision_device, signals: VisionTouchSignals):
        self.vision_device = vision_device
        self.signals = signals
        self.running = False
        self.thread = None
        
    def start(self):
        """Start data collection thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._collect_loop, daemon=True)
        self.thread.start()
        logger.info("VisionTouch data collection started")
        
    def stop(self):
        """Stop data collection thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("VisionTouch data collection stopped")
        
    def _collect_loop(self):
        """Data collection loop (~30 Hz)"""
        while self.running:
            try:
                # Collect multiple data types
                data = self.vision_device.collect_sensor_data(
                    VTSDataType.FORCE6D_VECTOR,
                    VTSDataType.DEPTH_MAP,
                    VTSDataType.RAW_IMG,
                    VTSDataType.CALIBRATE_IMG,
                    VTSDataType.WARPED_IMG,
                    VTSDataType.DIFF_IMG,
                    VTSDataType.MARKER_IMG,
                    VTSDataType.SLIP_STATE,
                    VTSDataType.XYZ_VECTOR,
                    VTSDataType.MARKER_ORIGIN_VECTOR,
                    VTSDataType.MARKER_CURRENT_VECTOR,
                    VTSDataType.MARKER_OFFSET_VECTOR,
                )
                
                # Emit signals for GUI update
                if VTSDataType.FORCE6D_VECTOR in data:
                    self.signals.force_data_ready.emit(data[VTSDataType.FORCE6D_VECTOR])
                
                if VTSDataType.DEPTH_MAP in data:
                    self.signals.depth_data_ready.emit(data[VTSDataType.DEPTH_MAP])
                
                # Collect images
                images = {}
                if VTSDataType.RAW_IMG in data:
                    images['raw'] = data[VTSDataType.RAW_IMG]
                if VTSDataType.CALIBRATE_IMG in data:
                    images['calibrate'] = data[VTSDataType.CALIBRATE_IMG]
                if VTSDataType.WARPED_IMG in data:
                    images['warped'] = data[VTSDataType.WARPED_IMG]
                if VTSDataType.DIFF_IMG in data:
                    images['diff'] = data[VTSDataType.DIFF_IMG]
                if VTSDataType.MARKER_IMG in data:
                    images['marker'] = data[VTSDataType.MARKER_IMG]
                
                if images:
                    self.signals.image_data_ready.emit(images)
                
                # Slip detection
                if VTSDataType.SLIP_STATE in data:
                    self.signals.slip_data_ready.emit(
                        data[VTSDataType.SLIP_STATE],
                        data.get(VTSDataType.WARPED_IMG)
                    )
                
                # XYZ vector
                if VTSDataType.XYZ_VECTOR in data:
                    self.signals.xyz_data_ready.emit(data[VTSDataType.XYZ_VECTOR])
                
                # Marker tracking
                if VTSDataType.MARKER_OFFSET_VECTOR in data:
                    self.signals.marker_data_ready.emit(
                        data[VTSDataType.MARKER_ORIGIN_VECTOR],
                        data[VTSDataType.MARKER_CURRENT_VECTOR],
                        data[VTSDataType.MARKER_OFFSET_VECTOR],
                        data.get(VTSDataType.WARPED_IMG)
                    )
                
                time.sleep(0.100)  # ~10 Hz (reduced to avoid UI thread lag)
                
            except VTSError as e:
                self.signals.error_occurred.emit(f"VTSError: {e}")
                logger.error(f"VisionTouch collection error: {e}")
                break
            except Exception as e:
                self.signals.error_occurred.emit(f"Error: {e}")
                logger.error(f"Unexpected error in VisionTouch collection: {e}")
                break


class Force6DWidget(QWidget):
    """6D Force/Torque display widget"""
    
    def __init__(self):
        super().__init__()
        self.current_values = np.zeros(6)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("6D Force & Torque")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Force group
        force_group = QGroupBox("Force (N)")
        force_layout = QGridLayout(force_group)
        force_layout.setSpacing(8)
        
        self.force_labels = {}
        force_names = ['Fx', 'Fy', 'Fz']
        force_colors = ['#e74c3c', '#27ae60', '#3498db']
        
        for i, (name, color) in enumerate(zip(force_names, force_colors)):
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 14px;")
            
            value_lbl = QLabel("0.00")
            value_lbl.setStyleSheet(
                "font-size: 18px; font-family: 'Courier New'; "
                "color: #2c3e50; background: #ecf0f1; padding: 4px 8px; border-radius: 4px;"
            )
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setMinimumWidth(100)
            
            force_layout.addWidget(name_lbl, i, 0)
            force_layout.addWidget(value_lbl, i, 1)
            self.force_labels[name] = value_lbl
        
        layout.addWidget(force_group)
        
        # Torque group
        torque_group = QGroupBox("Torque (N·m)")
        torque_layout = QGridLayout(torque_group)
        torque_layout.setSpacing(8)
        
        torque_names = ['Mx', 'My', 'Mz']
        torque_colors = ['#e67e22', '#9b59b6', '#1abc9c']
        
        for i, (name, color) in enumerate(zip(torque_names, torque_colors)):
            name_lbl = QLabel(f"{name}:")
            name_lbl.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 14px;")
            
            value_lbl = QLabel("0.000")
            value_lbl.setStyleSheet(
                "font-size: 18px; font-family: 'Courier New'; "
                "color: #2c3e50; background: #ecf0f1; padding: 4px 8px; border-radius: 4px;"
            )
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setMinimumWidth(100)
            
            torque_layout.addWidget(name_lbl, i, 0)
            torque_layout.addWidget(value_lbl, i, 1)
            self.force_labels[name] = value_lbl
        
        layout.addWidget(torque_group)
        
        # Add pyqtgraph visualization if available
        try:
            from .touch_panel_force import ForceTorqueFingerChart
            self.force_chart = ForceTorqueFingerChart("VisionTouch", (100, 255, 100))
            layout.addWidget(self.force_chart, 1)
        except ImportError as e:
            logger.warning(f"pyqtgraph or its dependencies (e.g. PyOpenGL) not available: {e}. Using simple display.")
            self.force_chart = None
        
        layout.addStretch()
        
    def update_data(self, force6d: np.ndarray):
        """Update 6D force display
        
        Args:
            force6d: np.ndarray of shape (6,) - [Fx, Fy, Fz, Mx, My, Mz]
        """
        if not self.isVisible():
            return
        if len(force6d) != 6:
            return
        
        self.current_values = force6d
        
        # Update text labels
        names = ['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz']
        for i, name in enumerate(names):
            if i < 3:  # Force
                self.force_labels[name].setText(f"{force6d[i]:+.2f}")
            else:  # Torque
                self.force_labels[name].setText(f"{force6d[i]:+.3f}")
        
        # Update chart if available
        if self.force_chart:
            self.force_chart.add_data(
                force6d[0], force6d[1], force6d[2],  # Fx, Fy, Fz
                force6d[3], force6d[4]  # Mx, My (chart only supports 5 params)
            )


class DepthMapWidget(QWidget):
    """Depth map heatmap display"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        title = QLabel("Depth Map")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image display
        self.image_label = QLabel("No depth data")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #2c3e50; color: #ecf0f1; font-size: 14px;")
        self.image_label.setMinimumSize(400, 300)
        layout.addWidget(self.image_label, 1)
        
    def update_data(self, depth_map: np.ndarray):
        """Update depth map visualization
        
        Args:
            depth_map: np.ndarray of shape (H, W), dtype=float32
        """
        if not self.isVisible():
            return
        if depth_map is None or depth_map.size == 0:
            return
        
        # Normalize to 0-255
        depth_max = max(1.0, np.max(depth_map))
        depth_norm = (depth_map / depth_max * 255).astype(np.uint8)
        
        # Apply colormap (convert to RGB)
        import cv2
        depth_colored = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        depth_rgb = cv2.cvtColor(depth_colored, cv2.COLOR_BGR2RGB)
        
        # Convert to QPixmap
        h, w, ch = depth_rgb.shape
        bytes_per_line = ch * w
        q_image = QImage(depth_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit label
        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)


class ImageViewWidget(QWidget):
    """Raw image display (Warped, Diff, Marker)"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        title = QLabel("Sensor Images")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image tabs
        self.image_tabs = QTabWidget()
        
        # Raw image
        self.raw_label = QLabel("No image")
        self.raw_label.setAlignment(Qt.AlignCenter)
        self.raw_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.raw_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.raw_label, "Raw")
        
        # Calibrate image
        self.calibrate_label = QLabel("No image")
        self.calibrate_label.setAlignment(Qt.AlignCenter)
        self.calibrate_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.calibrate_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.calibrate_label, "Calibrate")
        
        # Warped image
        self.warped_label = QLabel("No image")
        self.warped_label.setAlignment(Qt.AlignCenter)
        self.warped_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.warped_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.warped_label, "Warped")
        
        # Diff image
        self.diff_label = QLabel("No image")
        self.diff_label.setAlignment(Qt.AlignCenter)
        self.diff_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.diff_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.diff_label, "Diff")
        
        # Marker image
        self.marker_label = QLabel("No image")
        self.marker_label.setAlignment(Qt.AlignCenter)
        self.marker_label.setStyleSheet("background: #2c3e50; color: #ecf0f1;")
        self.marker_label.setMinimumSize(400, 300)
        self.image_tabs.addTab(self.marker_label, "Marker")
        
        layout.addWidget(self.image_tabs, 1)
        
    def update_data(self, images: dict):
        """Update image displays
        
        Args:
            images: dict with keys 'warped', 'diff', 'marker'
        """
        import cv2
        
        for key, label in [
            ('raw', self.raw_label),
            ('calibrate', self.calibrate_label),
            ('warped', self.warped_label),
            ('diff', self.diff_label),
            ('marker', self.marker_label)
        ]:
            if key in images:
                img = images[key]
                if img is not None and img.size > 0:
                    # Convert BGR to RGB
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    h, w, ch = img_rgb.shape
                    bytes_per_line = ch * w
                    q_image = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_image)
                    
                    # Scale to fit
                    scaled_pixmap = pixmap.scaled(
                        label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    label.setPixmap(scaled_pixmap)


class VisionTouchPanel(QWidget):
    """VisionTouch Independent Panel
    
    Displays VisionTouch sensor data. Can be embedded in other windows.
    Automatically connects to the first available VisionTouch device.
    """
    
    def __init__(self, parent=None, target_sn=None):
        super().__init__(parent)
        self.target_sn = target_sn
        
        self.vision_device: Optional[VTSensor] = None
        self.collector: Optional[VisionTouchDataCollector] = None
        self.signals = VisionTouchSignals()
        
        self._setup_ui()
        self._connect_signals()
        
        # Auto-connect on startup
        QTimer.singleShot(500, self._auto_connect)
        
    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Control bar
        control_bar = QWidget()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        control_layout.addWidget(self.connect_btn)
        
        self.calibrate_btn = QPushButton("📐 Calibrate")
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.calibrate_btn.setEnabled(False)
        control_layout.addWidget(self.calibrate_btn)
        
        control_layout.addStretch()
        
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        control_layout.addWidget(self.status_label)
        
        layout.addWidget(control_bar)
        
        # Main tabs
        self.tabs = QTabWidget()
        
        # Tab 1: 6D Force (Most important - force/torque data)
        self.force_widget = Force6DWidget()
        self.tabs.addTab(self.force_widget, "💪 6D Force")
        
        # Tab 2: Depth Map (Pressure distribution visualization)
        self.depth_widget = DepthMapWidget()
        self.tabs.addTab(self.depth_widget, "🗺 Depth Map")
        
        # Tab 3: Slip Detection (Practical feature for grasping)
        from .vision_touch_widgets import SlipDetectionWidget
        self.slip_widget = SlipDetectionWidget()
        self.tabs.addTab(self.slip_widget, "⚠ Slip Detection")
        
        # Tab 4: Images (Raw sensor images for debugging)
        self.image_widget = ImageViewWidget()
        self.tabs.addTab(self.image_widget, "📷 Images")
        
        # Tab 5: 3D View (Advanced visualization)
        from .vision_touch_widgets import PointCloud3DWidget
        self.pointcloud_widget = PointCloud3DWidget()
        self.tabs.addTab(self.pointcloud_widget, "🎨 3D View")
        
        # Tab 6: Marker Tracking (Advanced analysis)
        from .vision_touch_widgets import MarkerTrackingWidget
        self.marker_widget = MarkerTrackingWidget()
        self.tabs.addTab(self.marker_widget, "🎯 Marker")
        
        layout.addWidget(self.tabs, 1)
        
        # Status bar
        self.statusbar = QStatusBar()
        self.statusbar.showMessage("Ready")
        layout.addWidget(self.statusbar)
        
    def _connect_signals(self):
        """Connect signals to slots"""
        self.signals.force_data_ready.connect(self.force_widget.update_data)
        self.signals.depth_data_ready.connect(self.depth_widget.update_data)
        self.signals.image_data_ready.connect(self.image_widget.update_data)
        self.signals.slip_data_ready.connect(self.slip_widget.update_data)
        self.signals.xyz_data_ready.connect(self.pointcloud_widget.update_data)
        self.signals.marker_data_ready.connect(self.marker_widget.update_data)
        self.signals.status_message.connect(self._on_status_message)
        self.signals.error_occurred.connect(self._on_error)
        
    def _toggle_connection(self):
        """Toggle connection state"""
        if self.vision_device is not None:
            # We are connected, disconnect first
            self._disconnect()
            self.vision_device = None
            self.connect_btn.setText("🔌 Connect / Switch")
            self.status_label.setText("Disconnected")
            self.statusbar.showMessage("Disconnected from sensor")
            self.calibrate_btn.setEnabled(False)
        else:
            self._auto_connect()
            
    def _auto_connect(self):
        """Auto-connect to first available VisionTouch device"""
        if VTSensor is None or VTSDeviceFinder is None:
            self._on_error("VisionTouch SDK not available")
            return
        
        try:
            self.connect_btn.setEnabled(False)
            
            if MOCK_MODE:
                self.status_label.setText("Connecting (Mock Mode)...")
                self.statusbar.showMessage("🎭 Mock Mode: Simulating VisionTouch device...")
            else:
                self.status_label.setText("Searching for VisionTouch...")
            
            finder = VTSDeviceFinder()
            sns = finder.get_sns()
            
            if not sns:
                self._on_error("No VisionTouch device found")
                return
            
            sn = None
            if self.target_sn and self.target_sn in sns:
                sn = self.target_sn
            elif len(sns) == 1:
                sn = sns[0]
            else:
                # Multiple devices, show selection dialog
                sn, ok = QInputDialog.getItem(
                    self,
                    "Select VisionTouch Device",
                    "Multiple devices found. Select one to connect:",
                    sns,
                    0,  # current item index
                    False  # editable
                )
                if not ok or not sn:
                    self._on_error("Connection cancelled by user")
                    return
            mode_str = " (Mock)" if MOCK_MODE else ""
            logger.info(f"Found VisionTouch device: {sn}{mode_str}")
            
            config = finder.get_device_by_sn(sn)
            self.vision_device = VTSensor(config=config)
            
            # Calibrate
            self.statusbar.showMessage("Calibrating...")
            self.vision_device.calibrate()
            
            # Start data collection
            self.collector = VisionTouchDataCollector(self.vision_device, self.signals)
            self.collector.start()
            
            status_icon = "🎭" if MOCK_MODE else "✅"
            self.status_label.setText(f"{status_icon} Connected: {sn}{mode_str}")
            self.statusbar.showMessage(f"Connected to {sn}{mode_str}")
            self.connect_btn.setText("🔌 Disconnect")
            self.calibrate_btn.setEnabled(True)
            
            logger.info(f"VisionTouch connected: {sn}{mode_str}")
            
        except Exception as e:
            error_msg = f"Connection error: {e}"
            if hasattr(e, 'suggestion'):
                error_msg += f"\nSuggestion: {e.suggestion}"
            self._on_error(error_msg)
        finally:
            self.connect_btn.setEnabled(True)
            
    def _calibrate(self):
        """Recalibrate sensor (set new background)"""
        if not self.vision_device:
            return
        
        try:
            self.statusbar.showMessage("Calibrating...")
            self.vision_device.calibrate()
            self.statusbar.showMessage("Calibration complete")
            logger.info("VisionTouch recalibrated")
        except Exception as e:
            self._on_error(f"Calibration error: {e}")
            
    def _on_status_message(self, message: str):
        """Handle status message"""
        self.statusbar.showMessage(message)
        
    def _on_error(self, message: str):
        """Handle error messages"""
        self.status_label.setText(f"Error: {message}")
        self.status_label.setStyleSheet(f"color: {COLORS['danger']}; font-weight: bold;")
        logger.error(message)

    def _disconnect(self):
        """Clean up background thread and device"""
        if self.collector:
            self.collector.stop()
        if self.vision_device:
            try:
                self.vision_device.release()
            except Exception as e:
                logger.error(f"Error releasing VisionTouch device: {e}")

    def closeEvent(self, event):
        """Clean up background thread on close"""
        self._disconnect()
        event.accept()
        logger.info("VisionTouch window closed")

class VisionTouchWindow(QMainWindow):
    """Main window wrapper for VisionTouchPanel"""
    def __init__(self, parent=None, target_sn=None):
        super().__init__(parent)
        self.setWindowTitle("VisionTouch Sensor")
        self.setMinimumSize(900, 700)
        self.panel = VisionTouchPanel(self, target_sn=target_sn)
        self.setCentralWidget(self.panel)

    def closeEvent(self, event):
        self.panel.closeEvent(event)
        event.accept()
