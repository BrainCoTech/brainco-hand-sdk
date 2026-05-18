"""Universal Touch Panel - Auto-dispatches to correct touch sub-panel"""

from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from .capacitive_touch_panel import CapacitiveTouchPanel
from .pressure_touch_panel import PressureTouchPanel
from .i18n import tr

if TYPE_CHECKING:
    from .shared_data import SharedDataManager

class UniversalTouchPanel(QWidget):
    """Universal Touch Panel that automatically loads the correct touch sub-module."""
    
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Instantiate sub-panels
        self.capacitive_panel = CapacitiveTouchPanel()
        self.advanced_touch_panel = PressureTouchPanel()
        self.no_touch_label = QLabel(tr("touch_sensor"))
        self.no_touch_label.setAlignment(Qt.AlignCenter)
        self.no_touch_label.setStyleSheet("font-size: 16px; color: #888;")
        
        self.layout.addWidget(self.capacitive_panel)
        self.layout.addWidget(self.advanced_touch_panel)
        self.layout.addWidget(self.no_touch_label)
        
        # Hide all by default
        self.capacitive_panel.hide()
        self.advanced_touch_panel.hide()
        self.no_touch_label.show()
        
    def set_device(self, device, slave_id, device_info, shared_data=None):
        from common_imports import is_capacitive_touch, has_touch
        
        if not device or not device_info:
            self._set_mode('none')
            return
            
        hw_type = getattr(device_info, 'hardware_type', None)
        
        if not has_touch(hw_type):
            self._set_mode('none')
            return
            
        if is_capacitive_touch(hw_type):
            self._set_mode('capacitive', device, slave_id, device_info, shared_data)
        else:
            # Pressure, Force3D and ArrayPressure route to the advanced panel.
            self._set_mode('advanced', device, slave_id, device_info, shared_data)
            
    def _set_mode(self, mode: str, device=None, slave_id=None, device_info=None, shared_data=None):
        if mode == 'capacitive':
            self.no_touch_label.hide()
            self.advanced_touch_panel.hide()
            self.advanced_touch_panel.set_device(None, None, None, None) # Clear out the other side
            self.capacitive_panel.show()
            self.capacitive_panel.set_device(device, slave_id, device_info, shared_data)
        elif mode == 'advanced':
            self.no_touch_label.hide()
            self.capacitive_panel.hide()
            self.capacitive_panel.set_device(None, None, None, None)
            self.advanced_touch_panel.show()
            self.advanced_touch_panel.set_device(device, slave_id, device_info, shared_data)
        else:
            self.capacitive_panel.hide()
            self.advanced_touch_panel.hide()
            self.capacitive_panel.set_device(None, None, None, None)
            self.advanced_touch_panel.set_device(None, None, None, None)
            self.no_touch_label.show()
            
    def clear_device(self):
        """Clear device to stop timers when disconnecting."""
        if hasattr(self.capacitive_panel, 'clear_device'):
            self.capacitive_panel.clear_device()
        if hasattr(self.advanced_touch_panel, 'clear_device'):
            self.advanced_touch_panel.clear_device()
        self.set_device(None, None, None, None)
            
    def update_texts(self):
        self.no_touch_label.setText(tr("touch_sensor") + " N/A")
        # Pass to children
        if hasattr(self.capacitive_panel, 'update_texts'):
            self.capacitive_panel.update_texts()
        if hasattr(self.advanced_touch_panel, 'update_texts'):
            self.advanced_touch_panel.update_texts()
