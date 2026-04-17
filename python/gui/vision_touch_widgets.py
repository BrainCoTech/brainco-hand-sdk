"""VisionTouch Advanced Widgets

Advanced visualization widgets for VisionTouch sensor data:
- Slip Detection
- 3D Point Cloud
- Marker Tracking
"""

import sys
import numpy as np
from pathlib import Path
from collections import deque
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QGroupBox, QProgressBar, QPushButton, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .touch_common import logger, COLORS

# Check for pyqtgraph (for 3D visualization)
try:
    import pyqtgraph as pg
    import pyqtgraph.opengl as gl
    HAS_PYQTGRAPH = True
except ImportError as e:
    HAS_PYQTGRAPH = False
    logger.warning(f"pyqtgraph or its dependencies (e.g. PyOpenGL) not available: {e}. 3D visualization disabled.")


# ============================================================================
# Slip Detection Widget
# ============================================================================

class SlipDetectionWidget(QWidget):
    """Slip detection display and monitoring
    
    Shows real-time slip state with:
    - Status indicator (6 different states)
    - Live image with overlay
    - History bar (last 100 frames)
    - Statistics (total frames, slip events, slip rate)
    """
    
    def __init__(self):
        super().__init__()
        self.slip_history = deque(maxlen=100)
        self.total_frames = 0
        self.slip_count = 0
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("Slip Detection")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Status indicator (large)
        self.status_label = QLabel("⚪ NO_OBJ")
        self.status_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; "
            "background: #27ae60; color: white; "
            "padding: 16px; border-radius: 8px;"
        )
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(80)
        layout.addWidget(self.status_label)
        
        # Image display
        image_frame = QFrame()
        image_frame.setStyleSheet("background: #2c3e50; border-radius: 4px;")
        image_layout = QVBoxLayout(image_frame)
        
        self.image_label = QLabel("No image data")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("color: #ecf0f1; font-size: 14px;")
        self.image_label.setMinimumSize(500, 350)
        image_layout.addWidget(self.image_label)
        
        layout.addWidget(image_frame, 1)
        
        # History bar
        history_group = QGroupBox("Slip History (Last 100 frames)")
        history_layout = QVBoxLayout(history_group)
        
        self.history_bar = QProgressBar()
        self.history_bar.setRange(0, 100)
        self.history_bar.setValue(0)
        self.history_bar.setTextVisible(True)
        self.history_bar.setFormat("%v% slip detected")
        self.history_bar.setMinimumHeight(30)
        self.history_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #34495e;
                border-radius: 6px;
                background: #27ae60;
                text-align: center;
                font-size: 13px;
                font-weight: bold;
                color: white;
            }
            QProgressBar::chunk {
                background: #e74c3c;
                border-radius: 4px;
            }
        """)
        history_layout.addWidget(self.history_bar)
        
        layout.addWidget(history_group)
        
        # Statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(8)
        
        # Labels
        stats_layout.addWidget(QLabel("Total Frames:"), 0, 0)
        stats_layout.addWidget(QLabel("Slip Events:"), 1, 0)
        stats_layout.addWidget(QLabel("Slip Rate:"), 2, 0)
        
        # Values
        self.frames_label = QLabel("0")
        self.frames_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        stats_layout.addWidget(self.frames_label, 0, 1)
        
        self.slip_events_label = QLabel("0")
        self.slip_events_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e74c3c;")
        stats_layout.addWidget(self.slip_events_label, 1, 1)
        
        self.slip_rate_label = QLabel("0.0%")
        self.slip_rate_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #f39c12;")
        stats_layout.addWidget(self.slip_rate_label, 2, 1)
        
        stats_layout.setColumnStretch(1, 1)
        
        layout.addWidget(stats_group)
        
    def update_data(self, slip_state, image=None):
        """Update slip detection display
        
        Args:
            slip_state: Enum with .name attribute (NO_SLIP, SLIP_DETECTED)
            image: Optional warped image (np.ndarray)
        """
        if not self.isVisible():
            return
            
        self.total_frames += 1
        
        state_name = slip_state.name if hasattr(slip_state, 'name') else str(slip_state)
        is_slip = state_name in ("INCIPIENT_SLIP", "PARTIAL_SLIP", "COMPLETE_SLIP")
        
        # Mapping rules
        slip_map = {
            "NO_OBJ": ("⚪ NO OBJECT", "#95a5a6"),         # Gray
            "CONTACT": ("🔵 CONTACT", "#3498db"),           # Blue
            "STEADY_HOLD": ("🟢 STEADY HOLD", "#27ae60"),   # Green
            "INCIPIENT_SLIP": ("🟡 INCIPIENT SLIP", "#f39c12"), # Yellow/Orange
            "PARTIAL_SLIP": ("🟠 PARTIAL SLIP", "#e67e22"),   # Orange
            "COMPLETE_SLIP": ("🔴 COMPLETE SLIP", "#e74c3c")  # Red
        }
        
        display_text, bg_color = slip_map.get(state_name, (f"⚪ {state_name}", "#7f8c8d"))
        
        if is_slip:
            self.slip_count += 1
            
        self.status_label.setText(display_text)
        self.status_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; "
            f"background: {bg_color}; color: white; "
            "padding: 16px; border-radius: 8px;"
        )
        
        # Update history
        self.slip_history.append(1 if is_slip else 0)
        if len(self.slip_history) > 0:
            slip_percentage = int(sum(self.slip_history) / len(self.slip_history) * 100)
            self.history_bar.setValue(slip_percentage)
        
        # Update statistics
        self.frames_label.setText(str(self.total_frames))
        self.slip_events_label.setText(str(self.slip_count))
        
        if self.total_frames > 0:
            slip_rate = (self.slip_count / self.total_frames * 100)
            self.slip_rate_label.setText(f"{slip_rate:.2f}%")
        
        # Update image with overlay
        if image is not None:
            self._update_image(image, slip_state.name)
    
    def _update_image(self, image, state_text):
        """Update image with slip state overlay"""
        try:
            import cv2
            img_copy = image.copy()
            
            # Map state to BGR color
            color_map = {
                "NO_OBJ": (128, 128, 128),       # Gray
                "CONTACT": (255, 0, 0),          # Blue
                "STEADY_HOLD": (0, 255, 0),      # Green
                "INCIPIENT_SLIP": (0, 255, 255), # Yellow
                "PARTIAL_SLIP": (0, 165, 255),   # Orange
                "COMPLETE_SLIP": (0, 0, 255)     # Red
            }
            color = color_map.get(state_text, (255, 255, 255))
            font = cv2.FONT_HERSHEY_SIMPLEX
            
            # Main status text
            cv2.putText(img_copy, state_text, (10, 40),
                       font, 1.2, color, 3)
            
            # Frame counter
            cv2.putText(img_copy, f"Frame: {self.total_frames}", (10, 80),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Convert to QPixmap
            img_rgb = cv2.cvtColor(img_copy, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            q_image = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            # Scale to fit
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
        except Exception as e:
            logger.error(f"Error updating slip image: {e}")
    
    def clear(self):
        """Clear all data"""
        self.slip_history.clear()
        self.total_frames = 0
        self.slip_count = 0
        self.status_label.setText("⚪ NO_OBJ")
        self.history_bar.setValue(0)
        self.frames_label.setText("0")
        self.slip_events_label.setText("0")
        self.slip_rate_label.setText("0.0%")
        self.image_label.clear()
        self.image_label.setText("No image data")


# ============================================================================
# 3D Point Cloud Widget
# ============================================================================

class PointCloud3DWidget(QWidget):
    """3D point cloud visualization using PyQtGraph
    
    Displays XYZ vector data as interactive 3D point cloud with:
    - Rotation, zoom, pan controls
    - Color-coded by depth
    - View presets (Top, Side, Front)
    - Point count and depth range info
    """
    
    def __init__(self):
        super().__init__()
        self.has_3d = HAS_PYQTGRAPH
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("3D Point Cloud Visualization")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        if not self.has_3d:
            # Show installation message
            msg = QLabel(
                "⚠ PyQtGraph not installed\n\n"
                "Install with: pip install pyqtgraph\n\n"
                "3D visualization requires pyqtgraph for OpenGL rendering."
            )
            msg.setStyleSheet(
                "font-size: 14px; color: #e67e22; "
                "background: #fef5e7; padding: 20px; border-radius: 8px;"
            )
            msg.setAlignment(Qt.AlignCenter)
            layout.addWidget(msg, 1)
            return
        
        # 3D view widget
        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setMinimumSize(600, 450)
        self.gl_widget.setCameraPosition(distance=100, elevation=30, azimuth=45)
        self.gl_widget.setBackgroundColor('#1a1a2e')
        
        # Add grid
        grid = gl.GLGridItem()
        grid.setSize(100, 100, 1)
        grid.setSpacing(10, 10, 1)
        self.gl_widget.addItem(grid)
        
        # Add axes
        axis = gl.GLAxisItem()
        axis.setSize(50, 50, 50)
        self.gl_widget.addItem(axis)
        
        # Point cloud scatter plot
        self.scatter = gl.GLScatterPlotItem()
        self.gl_widget.addItem(self.scatter)
        
        layout.addWidget(self.gl_widget, 1)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        reset_btn = QPushButton("🔄 Reset View")
        reset_btn.clicked.connect(self._reset_view)
        controls_layout.addWidget(reset_btn)
        
        top_btn = QPushButton("⬆ Top View")
        top_btn.clicked.connect(self._top_view)
        controls_layout.addWidget(top_btn)
        
        side_btn = QPushButton("➡ Side View")
        side_btn.clicked.connect(self._side_view)
        controls_layout.addWidget(side_btn)
        
        front_btn = QPushButton("👁 Front View")
        front_btn.clicked.connect(self._front_view)
        controls_layout.addWidget(front_btn)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Info label
        self.info_label = QLabel("Point Count: 0 | Depth Range: 0.0 - 0.0 mm")
        self.info_label.setStyleSheet("font-size: 13px; color: #7f8c8d;")
        layout.addWidget(self.info_label)
        
    def update_data(self, xyz_vector: np.ndarray):
        """Update 3D point cloud
        
        Args:
            xyz_vector: np.ndarray, shape=(N,M,3) - XYZ coordinates
        """
        if not self.isVisible() or not self.has_3d:
            return
        
        try:
            # Reshape to (N*M, 3)
            points = xyz_vector.reshape(-1, 3)
            
            # Extract coordinates
            x, y, z = points[:, 0], points[:, 1], points[:, 2]
            
            # Filter out invalid points (optional)
            valid_mask = ~np.isnan(x) & ~np.isnan(y) & ~np.isnan(z)
            points = points[valid_mask]
            x, y, z = points[:, 0], points[:, 1], points[:, 2]
            
            if len(points) == 0:
                return
            
            # Color by depth (z value)
            z_min, z_max = z.min(), z.max()
            z_range = z_max - z_min if z_max > z_min else 1.0
            z_norm = (z - z_min) / z_range
            
            # Create color array (RGBA)
            colors = np.zeros((len(z), 4))
            colors[:, 0] = z_norm  # Red channel (high depth)
            colors[:, 2] = 1 - z_norm  # Blue channel (low depth)
            colors[:, 3] = 0.8  # Alpha
            
            # Update scatter plot
            self.scatter.setData(pos=points, color=colors, size=6, pxMode=True)
            
            # Update info
            self.info_label.setText(
                f"Point Count: {len(points)} | "
                f"Depth Range: {z_min:.2f} - {z_max:.2f} mm"
            )
            
        except Exception as e:
            logger.error(f"Error updating 3D point cloud: {e}")
    
    def _reset_view(self):
        """Reset camera to default view"""
        if self.has_3d:
            self.gl_widget.setCameraPosition(distance=100, elevation=30, azimuth=45)
    
    def _top_view(self):
        """Set top-down view"""
        if self.has_3d:
            self.gl_widget.setCameraPosition(distance=100, elevation=90, azimuth=0)
    
    def _side_view(self):
        """Set side view"""
        if self.has_3d:
            self.gl_widget.setCameraPosition(distance=100, elevation=0, azimuth=90)
    
    def _front_view(self):
        """Set front view"""
        if self.has_3d:
            self.gl_widget.setCameraPosition(distance=100, elevation=0, azimuth=0)
    
    def clear(self):
        """Clear point cloud"""
        if self.has_3d:
            self.scatter.setData(pos=np.array([]), color=np.array([]))
            self.info_label.setText("Point Count: 0 | Depth Range: 0.0 - 0.0 mm")


# ============================================================================
# Marker Tracking Widget
# ============================================================================

class MarkerTrackingWidget(QWidget):
    """Marker tracking visualization
    
    Shows marker movement with:
    - Image with marker overlay (origin, current, offset vectors)
    - Marker grid info
    - Offset statistics
    - Estimated shear force
    """
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Title
        title = QLabel("Marker Tracking")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #5D9CEC;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Image display
        image_frame = QFrame()
        image_frame.setStyleSheet("background: #2c3e50; border-radius: 4px;")
        image_layout = QVBoxLayout(image_frame)
        
        self.image_label = QLabel("No marker data")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("color: #ecf0f1; font-size: 14px;")
        self.image_label.setMinimumSize(600, 400)
        image_layout.addWidget(self.image_label)
        
        # Legend
        legend = QLabel(
            "🟢 Green: Origin  |  🔴 Red: Current  |  🔵 Blue: Offset Vector"
        )
        legend.setStyleSheet("font-size: 12px; color: #95a5a6;")
        legend.setAlignment(Qt.AlignCenter)
        image_layout.addWidget(legend)
        
        layout.addWidget(image_frame, 1)
        
        # Info group
        info_group = QGroupBox("Tracking Information")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(8)
        
        # Grid info
        info_layout.addWidget(QLabel("Marker Grid:"), 0, 0)
        self.grid_label = QLabel("0×0 (0 points)")
        self.grid_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        info_layout.addWidget(self.grid_label, 0, 1)
        
        # Offset stats
        info_layout.addWidget(QLabel("Max Offset:"), 1, 0)
        self.max_offset_label = QLabel("0.00 px")
        self.max_offset_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        info_layout.addWidget(self.max_offset_label, 1, 1)
        
        info_layout.addWidget(QLabel("Avg Offset:"), 2, 0)
        self.avg_offset_label = QLabel("0.00 px")
        self.avg_offset_label.setStyleSheet("font-weight: bold; color: #f39c12;")
        info_layout.addWidget(self.avg_offset_label, 2, 1)
        
        # Shear force estimate
        info_layout.addWidget(QLabel("Shear Force Fx:"), 3, 0)
        self.shear_fx_label = QLabel("0.00 N")
        self.shear_fx_label.setStyleSheet("font-weight: bold; color: #3498db;")
        info_layout.addWidget(self.shear_fx_label, 3, 1)
        
        info_layout.addWidget(QLabel("Shear Force Fy:"), 4, 0)
        self.shear_fy_label = QLabel("0.00 N")
        self.shear_fy_label.setStyleSheet("font-weight: bold; color: #9b59b6;")
        info_layout.addWidget(self.shear_fy_label, 4, 1)
        
        info_layout.setColumnStretch(1, 1)
        
        layout.addWidget(info_group)
        
    def update_data(self, marker_origin, marker_current, marker_offset, image=None):
        """Update marker tracking display
        
        Args:
            marker_origin: np.ndarray, shape=(N,M,2) - origin positions
            marker_current: np.ndarray, shape=(N,M,2) - current positions
            marker_offset: np.ndarray, shape=(N,M,2) - offset vectors
            image: Optional background image
        """
        if not self.isVisible():
            return
            
        try:
            N, M, _ = marker_origin.shape
            total_points = N * M
            self.grid_label.setText(f"{N}×{M} ({total_points} points)")
            
            # Calculate offset statistics
            offsets = np.linalg.norm(marker_offset, axis=2)
            max_offset = np.max(offsets)
            avg_offset = np.mean(offsets)
            
            self.max_offset_label.setText(f"{max_offset:.2f} px")
            self.avg_offset_label.setText(f"{avg_offset:.2f} px")
            
            # Estimate shear force (simplified linear model)
            # Scale factor: pixels to Newtons (calibration dependent)
            scale_factor = 0.05  # Example: 0.05 N per pixel
            fx = np.mean(marker_offset[:, :, 0]) * scale_factor
            fy = np.mean(marker_offset[:, :, 1]) * scale_factor
            
            self.shear_fx_label.setText(f"{fx:+.2f} N")
            self.shear_fy_label.setText(f"{fy:+.2f} N")
            
            # Draw markers on image
            if image is not None:
                self._draw_markers(image, marker_origin, marker_current, marker_offset)
                
        except Exception as e:
            logger.error(f"Error updating marker tracking: {e}")
    
    def _draw_markers(self, image, origin, current, offset):
        """Draw markers and vectors on image"""
        try:
            import cv2
            img_copy = image.copy()
            
            N, M, _ = origin.shape
            
            # Draw threshold for arrows (only show significant offsets)
            arrow_threshold = 1.0  # pixels
            
            for i in range(N):
                for j in range(M):
                    # Origin point (green circle)
                    o_pt = tuple(origin[i, j].astype(int))
                    cv2.circle(img_copy, o_pt, 4, (0, 255, 0), -1)
                    cv2.circle(img_copy, o_pt, 5, (255, 255, 255), 1)
                    
                    # Current point (red circle)
                    c_pt = tuple(current[i, j].astype(int))
                    cv2.circle(img_copy, c_pt, 4, (0, 0, 255), -1)
                    cv2.circle(img_copy, c_pt, 5, (255, 255, 255), 1)
                    
                    # Offset arrow (blue) - only if significant
                    offset_mag = np.linalg.norm(offset[i, j])
                    if offset_mag > arrow_threshold:
                        cv2.arrowedLine(img_copy, o_pt, c_pt, (255, 0, 0), 2, tipLength=0.3)
            
            # Add info text
            cv2.putText(img_copy, f"Markers: {N}x{M}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            # Convert to QPixmap
            img_rgb = cv2.cvtColor(img_copy, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            q_image = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            # Scale to fit
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            
        except Exception as e:
            logger.error(f"Error drawing markers: {e}")
    
    def clear(self):
        """Clear all data"""
        self.grid_label.setText("0×0 (0 points)")
        self.max_offset_label.setText("0.00 px")
        self.avg_offset_label.setText("0.00 px")
        self.shear_fx_label.setText("0.00 N")
        self.shear_fy_label.setText("0.00 N")
        self.image_label.clear()
        self.image_label.setText("No marker data")
