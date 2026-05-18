"""Internationalization Support Module"""

from PySide6.QtCore import QObject, Signal, QSettings


class I18n(QObject):
    """Internationalization Manager"""

    language_changed = Signal(str)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        self._settings = QSettings("BrainCo", "StarkSDK")
        # Load saved language preference, default to "en"
        saved_lang = self._settings.value("language", "en")
        self._current_language = saved_lang if saved_lang in ("en", "zh") else "en"
        self._translations = {
            "en": TRANSLATIONS_EN,
            "zh": TRANSLATIONS_ZH
        }

    @property
    def current_language(self):
        return self._current_language

    def set_language(self, lang: str):
        """Set language and persist preference"""
        if lang in self._translations:
            self._current_language = lang
            self._settings.setValue("language", lang)
            self.language_changed.emit(lang)

    def translate(self, key: str) -> str:
        """Get translated text"""
        translations = self._translations.get(self._current_language, TRANSLATIONS_EN)
        return translations.get(key, key)


# English translations
TRANSLATIONS_EN = {
    # Main window
    "app_title": "Stark SDK GUI",
    "menu_file": "File",
    "menu_help": "Help",
    "menu_exit": "Exit",
    "menu_about": "About",
    "menu_language": "Language",
    "lang_english": "English",
    "lang_chinese": "中文",
    "status_disconnected": "Disconnected",
    "status_connected": "Connected",
    "ready": "Ready",

    # About dialog
    "about_title": "About Stark SDK GUI",
    "about_text": (
        "Stark SDK Unified GUI Tool\n\n"
        "Supported Protocols:\n"
        "- Modbus/RS485\n"
        "- CAN 2.0\n"
        "- CANFD\n"
        "- EtherCAT\n\n"
        "Supported Devices:\n"
        "- Revo1 Basic/Touch\n"
        "- Revo1 Advanced/AdvancedTouch\n"
        "- Revo2 Basic/Touch\n\n"
        "© 2026 BrainCo"
    ),

    # Connection panel
    "connection_settings": "Connection Settings",
    "connection_info": "Connection Info",
    "protocol": "Protocol",
    "modbus_params": "Modbus Parameters",
    "serial_port": "Serial Port",
    "port": "Port",
    "baudrate": "Baudrate",
    "baud": "Baud",
    "slave_id": "Slave ID",
    "id": "ID",
    "can_params": "CAN Parameters",
    "adapter": "Adapter",
    "channel": "Channel",
    "btn_connect": "Connect",
    "btn_disconnect": "Disconnect",
    "btn_auto_detect": "🔍 Auto Detect",
    "status_connecting": "Connecting...",
    "status_connect_failed": "Connection failed",
    "error_sdk_not_installed": "Error: bc_stark_sdk not installed",
    "error_not_implemented": "Error: {protocol} not implemented",

    # Motor control panel
    "motor_control": "Motor Control",
    "control_mode": "Control Mode",
    "mode": "Mode",
    "mode_position": "Position",
    "mode_speed": "Speed",
    "or_speed": "or Speed",
    "speed_priority_tooltip": "If > 0, speed API will override T(ms)",
    "mode_current": "Current",
    "mode_torque": "Torque Control",
    "finger_control": "Finger Control",
    "finger_thumb": "Thumb",
    "finger_index": "Index",
    "finger_middle": "Middle",
    "finger_ring": "Ring",
    "finger_pinky": "Pinky",
    "current": "Current",
    "global_control": "Global Control",
    "btn_open_all": "Open All",
    "btn_close_all": "Close All",
    "btn_stop_all": "Stop All",
    "btn_zero_all": "Zero All",

    # Touch sensor panel
    "touch_sensor": "Touch Sensor",
    "touch_control": "Touch Control",
    "btn_enable_touch": "Enable Touch",
    "btn_calibrate": "Calibrate",
    "btn_reset": "Reset",
    "finger_selection": "Finger Selection",
    "touch_data": "Touch Data",
    "pressure_touch": "Pressure Touch",
    "normal_force": "Normal Force",
    "tangential_force": "Tangential Force",
    "proximity": "Proximity",
    "status": "Status",

    # Touch sensor confirmation dialogs
    "dialog_calibrate_title": "Confirm Calibration",
    "dialog_calibrate_message": (
        "Are you sure you want to calibrate the touch sensors?\n\n"
        "Purpose: Recalibrates the touch sensor baseline values to improve accuracy.\n\n"
        "Effects:\n"
        "• Resets the zero-point reference for force measurements\n"
        "• Should be performed when sensors show drift or inaccurate readings\n"
        "• Fingers should be in a relaxed, unloaded state during calibration\n\n"
        "This operation takes a few seconds to complete."
    ),
    "dialog_reset_title": "Confirm Reset",
    "dialog_reset_message": (
        "Are you sure you want to reset the touch sensors?\n\n"
        "Purpose: Resets touch sensors to their default factory state.\n\n"
        "Effects:\n"
        "• Clears all calibration data\n"
        "• Restores default sensor parameters\n"
        "• May require re-calibration after reset\n\n"
        "This operation cannot be undone."
    ),

    # Data collection panel
    "data_collection": "Data Collection",
    "collection_settings": "Collection Settings",
    "frequency_hz": "Frequency (Hz)",
    "duration_sec": "Duration (sec)",
    "save_path": "Save Path",
    "data_types": "Data Types",
    "motor_status": "Motor Status",
    "touch_data_type": "Touch Data",
    "btn_start_collection": "Start Collection",
    "btn_stop_collection": "Stop Collection",
    "collection_status": "Collection Status",
    "status_not_started": "Not started",
    "status_collecting": "Collecting",
    "status_completed": "Completed",
    "log_start_collection": "Starting collection...",
    "log_stop_collection": "Collection stopped",
    "log_save_to": "Saving to: {path}",
    "log_collection_done": "Collection completed, {count} records",
    "log_collection_failed": "Collection failed: {error}",
    "log": "Log",

    # System config panel
    "system_config": "System Config",
    "device_info": "Device Info",
    "serial_number": "Serial Number",
    "firmware_version": "Firmware Version",
    "hardware_type": "Hardware Type",
    "slave_id_settings": "Slave ID Settings",
    "new_slave_id": "New Slave ID",
    "system_control": "System Control",
    "btn_reboot": "Reboot Device",
    "btn_factory_reset": "Factory Reset",
    "operation_log": "Operation Log",
    "confirm": "Confirm",
    "confirm_factory_reset": "Are you sure to factory reset? This cannot be undone!",
    "log_setting_slave_id": "Setting slave ID to {id}...",
    "log_slave_id_set": "Slave ID set to {id}",
    "log_slave_id_failed": "Failed to set slave ID: {error}",
    "log_rebooting": "Rebooting device...",
    "log_rebooted": "Device rebooted",
    "log_reboot_failed": "Reboot failed: {error}",
    "log_factory_resetting": "Factory resetting...",
    "log_factory_reset_done": "Factory reset completed",
    "log_factory_reset_failed": "Factory reset failed: {error}",

    # Action sequence panel
    "action_sequence": "Action Sequence",
    "preset_actions": "Preset Actions",
    "preset": "Preset",
    "btn_load": "Load",
    "action_list": "Action List",
    "action_index": "Index",
    "action_duration": "Duration (ms)",
    "action_mode": "Mode",
    "action_positions": "Positions",
    "action_durations": "Durations",
    "btn_add": "Add",
    "btn_remove": "Remove",
    "btn_clear": "Clear",
    "execute_control": "Execute Control",
    "custom_slot": "Custom Slot",
    "btn_upload": "Upload",
    "btn_run": "Run",
    "btn_stop": "Stop",
    "file_operations": "File Operations",
    "btn_import": "Import",
    "btn_export": "Export",
    "success": "Success",
    "error": "Error",
    "upload_success": "Action sequence uploaded successfully",
    "upload_failed": "Upload failed",
    "run_failed": "Run failed",
    "import_failed": "Import failed",
    "export_failed": "Export failed",

    # Realtime monitor panel
    "realtime_monitor": "Realtime Monitor",
    "config": "Config",
    "time_window": "Time Window",
    "update_rate": "Update Rate",
    "control": "Control",
    "statistics": "Statistics",
    "frequency": "Frequency",
    "latency": "Latency",
    "packets": "Packets",
    "errors": "Errors",
    "speed": "Speed",
    "touch_force": "Touch Force",
    "hand_visualization": "Hand Visualization",

    # Timing test panel
    "timing_test": "Timing Test",
    "test_config": "Test Configuration",
    "test_mode": "Test Mode",
    "mode_all_fingers": "All Fingers",
    "mode_single_finger": "Single Finger",
    "finger_label": "Finger:",
    "num_cycles": "Number of Cycles",
    "timeout_sec": "Timeout (sec)",
    "read_freq": "Read Freq",
    "chart_freq": "Chart Freq",
    "avg_latency": "Avg Latency",
    "no_chart_available": "pyqtgraph not installed - no chart available",
    "btn_start_test": "Start Test",
    "btn_stop_test": "Stop Test",
    "test_results": "Test Results",
    "position": "Position",
    "time_sec": "Time (s)",
    "position_tracking": "Position Tracking",
    "test_starting": "Starting test...",
    "moving_to_initial": "Moving to initial position...",
    "cycle": "Cycle",
    "testing_close": "Testing close...",
    "testing_open": "Testing open...",
    "close_time": "Close time",
    "open_time": "Open time",
    "test_summary": "Test Summary",
    "avg_close_time": "Avg close time",
    "avg_open_time": "Avg open time",
    "min_close_time": "Min close time",
    "max_close_time": "Max close time",
    "min_open_time": "Min open time",
    "max_open_time": "Max open time",
    "test_completed": "Test completed",
    "test_failed": "Test failed",

    # DFU panel
    "dfu_upgrade": "DFU Upgrade",
    "dfu_warning_title": "⚠ Firmware Upgrade Notice",
    "dfu_warning_1": "1. Do not disconnect power or USB cable during upgrade",
    "dfu_warning_2": "2. Do not operate the device during upgrade",
    "dfu_warning_3": "3. Device will automatically restart after upgrade",
    "device_type": "Device Type",
    "current_firmware": "Current Firmware",
    "firmware_type": "Firmware Type",
    "firmware_file": "Firmware File",
    "btn_browse": "Browse...",
    "dfu_status_waiting": "Waiting to start",
    "dfu_status_idle": "Status: Idle",
    "btn_start_upgrade": "🚀 Start Upgrade",
    "btn_reset_state": "🔄 Reset State",
    "dfu_reset_tooltip": "Click to reset if DFU shows 'dfu is not available'",
    "dfu_progress": "Upgrade Progress",
    "dfu_select_file": "Please select firmware file",
    "dfu_starting": "Starting upgrade...",
    "dfu_completed": "Upgrade completed",
    "dfu_failed": "Upgrade failed",

    # Missing DFU keys
    "dfu_state_idle": "Idle",
    "dfu_state_starting": "Starting",
    "dfu_state_started": "Started",
    "dfu_state_transferring": "Transferring",
    "dfu_state_completed": "Completed",
    "dfu_state_aborted": "Aborted",
    "dfu_success_reboot": "Firmware upgrade successful! Device will restart.",
    "dfu_aborted": "Firmware upgrade aborted",
    "dfu_timeout": "Upgrade timeout, state: {state}",
    "dfu_fail_msg": "Upgrade failed: {error}",
    "device_type_none": "Device Type: --",
    "current_firmware_none": "Current FW: --",
    "select_firmware_file_title": "Select Firmware File",
    "error_no_device": "Please connect a device first",
    "error_invalid_file": "Please select a valid firmware file",
    "dfu_confirm_title": "Confirm Upgrade",
    "dfu_confirm_msg": "Are you sure you want to start the firmware upgrade?\n\nDo NOT disconnect or power off during the upgrade.",
    "dfu_upgrading": "Upgrading...",
    "dfu_state_prefix": "State: ",
    "dfu_upgrading_progress": "Upgrading... {percent}%",
    "dfu_state_unknown": "Unknown({state})",
    "dfu_success_short": "✅ Upgrade successful, device restarting",
    "dfu_failed_short": "❌ Upgrade failed",
    "dfu_reset_success_title": "Success",
    "dfu_reset_success_msg": "DFU state reset, ready to start over.",
    "dfu_reset_fail_msg": "Reset failed: {error}",
    "dfu_state_reset": "State reset successfully",

    "dfu_overlay_warning": "⚠ Firmware upgrading, do not operate...",
    "dfu_status_warning": "⚠ DFU upgrading, do not disconnect...",
    "dfu_wait_reconnect": "DFU completed - Waiting for device to restart and reconnect...",
    "status_connection_lost": "⚠ Connection lost - device might be disconnected",
    "status_reconnecting": "Reconnecting to device...",

    # Action Sequence Panel
    "action_fist": "Fist",
    "action_open": "Open",
    "action_pinch_two": "Pinch Two",
    "action_pinch_three": "Pinch Three",
    "action_pinch_side": "Pinch Side",
    "action_point": "Point",
    "action_wave": "Wave",

    # Motor settings
    "turbo_mode": "Turbo Mode",
    "enable_turbo": "Enable Turbo Mode",
    "turbo_interval": "Interval (ms)",
    "turbo_duration": "Duration (ms)",
    "position_calibration": "Position Calibration",
    "auto_calibration": "Auto Calibration on Power-up",
    "manual_calibration": "Manual Calibration",
    "force_level": "Force Level",
    "force_small": "Small",
    "force_normal": "Normal",
    "force_full": "Full",
    "unit_mode": "Unit Mode",
    "unit_normalized": "Normalized (0-1000)",
    "unit_physical": "Physical (degrees/mA)",
    "peripheral_settings": "Peripheral Settings",
    "led": "LED",
    "buzzer": "Buzzer",
    "vibration": "Vibration",
    "refresh_settings": "Refresh Settings",

    # Communication settings
    "modbus_baudrate": "Modbus/RS485 Baudrate",
    "canfd_baudrate": "CANFD Data Baudrate",
    "current_settings": "Current Settings",
    "confirm_baudrate_change": "Confirm Baudrate Change",
    "device_will_reboot": "Device will reboot after change.",

    # Finger settings (Revo2)
    "finger_settings": "Finger Settings (Revo2)",
    "protected_currents": "Protected Currents (Revo2)",
    "min_position": "Min Position",
    "max_position": "Max Position",
    "max_speed": "Max Speed",
    "max_current": "Max Current",
    "protected_current": "Protected Current",
    "apply": "Apply",
    "apply_all": "Apply All",
    "finger_thumb_base": "Thumb Base",
    "finger_thumb_aux": "Thumb Aux",

    "v3_settings": "⚙ Settings",

    "v3_position_limits": "Position Limits",
    "v3_speed_limits": "Speed Limits",
    "v3_joint_protect_current": "Joint Protect Current",
    "v3_global_settings": "Global Settings",
    "v3_global_protect_current": "Global Protect Current",
    "v3_auto_refresh": "Auto Refresh (3s)",
    "v3_read_parameters": "Read Parameters",
    "btn_apply": "Apply",
    "btn_set": "Set",
    "v3_joint_pos_limits": "Joint Pos Limits (°)",
    "v3_joint_speed_limits": "Joint Speed Limits (rpm)",
    "v3_calibration_current": "Calibration Current (A)",
    "v3_max_continuous_current": "Max Continuous Current (A)",
    "v3_auto_calibration": "Enable Auto Calibration",
    "v3_manual_calibration": "🔧 Manual Calibration",
    "v3_clear_errors": "🗑 Clear Motor Errors",
    "btn_open": "Open",
    "btn_close": "Close",
    "btn_run_finger": "▶ Run Finger",
    "v3_hw": "Hardware",
    "v3_fw": "Firmware",
    "v3_sn": "Serial No.",
    "v3_online": "Online Nodes",
    "v3_offline": "Offline Nodes",
    "v3_temp": "Max Temp",
    "v3_errors": "Error Nodes",
    "v3_max_temp": "Max",
    "v3_overheat": "Overheat!",
    "v3_warm": "Warm",
    "v3_no_errors": "No Errors",

    # Modes
    "mode_impedance": "Impedance",
    "mode_damping": "Damping",
    "mode_mit": "MIT",
    "mode_trajectory": "Trajectory Planning",
    "communication": "Communication",

    "system_state": "System State",
    "error_code": "Error Code",
    "current_ma": "Current (mA)",
    "voltage_v": "Voltage (V)",
    "power_w": "Power (W)",
    "temperature_c": "Temperature (°C)",
    "motor_info": "Motor Info",
    "motor_id": "Motor ID",
    "motor": "Motor",

    "timing_step": "Step",

    # Touch Sensor Panel
    "touch_summary": "Summary",
    "touch_palm": "Palm",
    "touch_thumb": "Thumb",
    "touch_index": "Index",
    "touch_middle": "Middle",
    "touch_ring": "Ring",
    "touch_pinky": "Pinky",

    # Timing Test
    "timing_control": "Control",
    "timing_signal": "Signal",
    "timing_sine": "Sine",
    "timing_square": "Square",
    "timing_triangle": "Triangle",

    # System Config
    "config_modbus": "Modbus",

    "v3_reset_finger_defaults": "↩ Reset Finger Defaults",
    "v3_touch_screen": "Touch Screen",
    "v3_teaching_mode": "🎓 Teaching Mode",
    "v3_software_e_stop": "🛑 Software E-Stop",
    "v3_use_broadcast_id": "Use Broadcast ID",
    "v3_diagnostics": "📊 Hardware Diagnostics",
    "v3_diag_read": "Read Info",
    "v3_motor_status_info": "Motor Status",

    # Teaching panel
    "teaching_mode": "Teaching Mode",
    "teaching_controls": "Controls",
    "teaching_record": "Record",
    "teaching_stop": "Stop",
    "teaching_play": "Playback",
    "teaching_save": "Save",
    "teaching_load": "Load",
    "teaching_save_title": "Save Trajectory",
    "teaching_load_title": "Load Trajectory",
    "teaching_record_freq": "Record Freq:",
    "teaching_playback_speed": "Speed:",
    "teaching_loop_count": "Loops:",
    "teaching_status": "Status",
    "teaching_state_idle": "Idle",
    "teaching_state_recording": "Recording...",
    "teaching_state_playing": "Playing...",
    "teaching_trajectory_info": "Trajectory Info",
}


# Chinese translations
TRANSLATIONS_ZH = {
    # Main window
    "app_title": "Stark SDK 控制台",
    "menu_file": "文件",
    "menu_help": "帮助",
    "menu_exit": "退出",
    "menu_about": "关于",
    "menu_language": "语言",
    "lang_english": "English",
    "lang_chinese": "中文",
    "status_disconnected": "未连接",
    "status_connected": "已连接",
    "ready": "就绪",

    # About Dialog
    "about_title": "关于 Stark SDK GUI",
    "about_text": (
        "Stark SDK 统一图形界面工具\n\n"
        "支持协议:\n"
        "- Modbus/RS485\n"
        "- CAN 2.0\n"
        "- CANFD\n"
        "- EtherCAT\n\n"
        "支持设备:\n"
        "- Revo1 Basic/Touch\n"
        "- Revo1 Advanced/AdvancedTouch\n"
        "- Revo2 Basic/Touch\n\n"
        "© 2026 BrainCo"
    ),

    # Connection Panel
    "connection_settings": "连接设置",
    "connection_info": "连接信息",
    "protocol": "协议",
    "modbus_params": "Modbus 参数",
    "serial_port": "串口",
    "port": "端口",
    "baudrate": "波特率",
    "baud": "波特率",
    "slave_id": "从站ID",
    "id": "ID",
    "can_params": "CAN 参数",
    "adapter": "适配器",
    "channel": "通道",
    "btn_connect": "连接",
    "btn_disconnect": "断开",
    "btn_auto_detect": "🔍 自动检测",
    "status_connecting": "连接中...",
    "status_connect_failed": "连接失败",
    "error_sdk_not_installed": "错误: bc_stark_sdk 未安装",
    "error_not_implemented": "错误: {protocol} 尚未实现",

    # Motor Control Panel
    "motor_control": "电机控制",
    "control_mode": "控制模式",
    "mode": "模式",
    "mode_position": "位置",
    "mode_speed": "速度",
    "or_speed": "或 Speed",
    "speed_priority_tooltip": "如果大于0，则优先使用速度规划（覆盖T）",
    "mode_current": "电流",
    "mode_torque": "力矩控制",
    "finger_control": "手指控制",
    "finger_thumb": "拇指",
    "finger_index": "食指",
    "finger_middle": "中指",
    "finger_ring": "无名指",
    "finger_pinky": "小指",
    "current": "电流",
    "global_control": "全局控制",
    "btn_open_all": "全部张开",
    "btn_close_all": "全部闭合",
    "btn_stop_all": "全部停止",
    "btn_zero_all": "全部归零",

    # Touch Sensor Panel
    "touch_sensor": "触觉传感器",
    "touch_control": "触觉控制",
    "btn_enable_touch": "启用触觉",
    "btn_calibrate": "校准",
    "btn_reset": "复位",
    "finger_selection": "手指选择",
    "touch_data": "触觉数据",
    "pressure_touch": "压力触觉",
    "normal_force": "法向力",
    "tangential_force": "切向力",
    "proximity": "接近值",
    "status": "状态",

    # Touch Sensor Confirmation Dialogs
    "dialog_calibrate_title": "确认校准",
    "dialog_calibrate_message": (
        "确定要校准触觉传感器吗？\n\n"
        "用途：重新校准触觉传感器的基准值，以提高测量精度。\n\n"
        "影响：\n"
        "• 重置力测量的零点参考值\n"
        "• 当传感器出现漂移或读数不准确时应执行此操作\n"
        "• 校准期间手指应处于放松、无负载状态\n\n"
        "此操作需要几秒钟完成。"
    ),
    "dialog_reset_title": "确认复位",
    "dialog_reset_message": (
        "确定要复位触觉传感器吗？\n\n"
        "用途：将触觉传感器恢复到默认出厂状态。\n\n"
        "影响：\n"
        "• 清除所有校准数据\n"
        "• 恢复默认传感器参数\n"
        "• 复位后可能需要重新校准\n\n"
        "此操作无法撤销。"
    ),

    # Data Collection Panel
    "data_collection": "数据采集",
    "collection_settings": "采集设置",
    "frequency_hz": "采集频率 (Hz)",
    "duration_sec": "采集时长 (秒)",
    "save_path": "保存路径",
    "data_types": "数据类型",
    "motor_status": "电机状态",
    "touch_data_type": "触觉数据",
    "btn_start_collection": "开始采集",
    "btn_stop_collection": "停止采集",
    "collection_status": "采集状态",
    "status_not_started": "未开始",
    "status_collecting": "采集中",
    "status_completed": "已完成",
    "log_start_collection": "开始采集...",
    "log_stop_collection": "停止采集",
    "log_save_to": "保存到: {path}",
    "log_collection_done": "采集完成，共 {count} 条数据",
    "log_collection_failed": "采集失败: {error}",
    "log": "日志",

    # System Config Panel
    "system_config": "系统配置",
    "device_info": "设备信息",
    "serial_number": "序列号",
    "firmware_version": "固件版本",
    "hardware_type": "硬件类型",
    "slave_id_settings": "从站ID设置",
    "new_slave_id": "新从站ID",
    "system_control": "系统控制",
    "btn_reboot": "重启设备",
    "btn_factory_reset": "恢复出厂设置",
    "operation_log": "操作日志",
    "confirm": "确认",
    "confirm_factory_reset": "确定要恢复出厂设置吗？此操作不可撤销！",
    "log_setting_slave_id": "设置从站ID为 {id}...",
    "log_slave_id_set": "从站ID已设置为 {id}",
    "log_slave_id_failed": "设置从站ID失败: {error}",
    "log_rebooting": "重启设备...",
    "log_rebooted": "设备已重启",
    "log_reboot_failed": "重启失败: {error}",
    "log_factory_resetting": "恢复出厂设置...",
    "log_factory_reset_done": "已恢复出厂设置",
    "log_factory_reset_failed": "恢复出厂设置失败: {error}",

    # Action Sequence Panel
    "action_sequence": "动作序列",
    "preset_actions": "预设动作",
    "preset": "预设",
    "btn_load": "加载",
    "action_list": "动作列表",
    "action_index": "序号",
    "action_duration": "时长 (ms)",
    "action_mode": "模式",
    "action_positions": "位置",
    "action_durations": "时长",
    "btn_add": "添加",
    "btn_remove": "移除",
    "btn_clear": "清空",
    "execute_control": "执行控制",
    "custom_slot": "自定义槽位",
    "btn_upload": "上传",
    "btn_run": "运行",
    "btn_stop": "停止",
    "file_operations": "文件操作",
    "btn_import": "导入",
    "btn_export": "导出",
    "success": "成功",
    "error": "错误",
    "upload_success": "动作序列上传成功",
    "upload_failed": "上传失败",
    "run_failed": "运行失败",
    "import_failed": "导入失败",
    "export_failed": "导出失败",

    # Realtime Monitor Panel
    "realtime_monitor": "实时监控",
    "config": "配置",
    "time_window": "时间窗口",
    "update_rate": "更新频率",
    "control": "控制",
    "statistics": "统计",
    "frequency": "频率",
    "latency": "延迟",
    "packets": "数据包",
    "errors": "错误",
    "speed": "速度",
    "touch_force": "触觉力",
    "hand_visualization": "手部可视化",

    # Timing Test Panel
    "timing_test": "时序测试",
    "test_config": "测试配置",
    "test_mode": "测试模式",
    "mode_all_fingers": "所有手指",
    "mode_single_finger": "单指测试",
    "finger_label": "手指:",
    "num_cycles": "循环次数",
    "timeout_sec": "超时时间 (秒)",
    "read_freq": "读取频率",
    "chart_freq": "图表刷新率",
    "avg_latency": "平均延迟",
    "no_chart_available": "未安装 pyqtgraph - 无法显示图表",
    "btn_start_test": "开始测试",
    "btn_stop_test": "停止测试",
    "test_results": "测试结果",
    "position": "位置",
    "time_sec": "时间 (秒)",
    "position_tracking": "位置追踪",
    "test_starting": "开始测试...",
    "moving_to_initial": "移动到初始位置...",
    "cycle": "循环",
    "testing_close": "测试闭合...",
    "testing_open": "测试张开...",
    "close_time": "闭合时间",
    "open_time": "张开时间",
    "test_summary": "测试总结",
    "avg_close_time": "平均闭合时间",
    "avg_open_time": "平均张开时间",
    "min_close_time": "最小闭合时间",
    "max_close_time": "最大闭合时间",
    "min_open_time": "最小张开时间",
    "max_open_time": "最大张开时间",
    "test_completed": "测试完成",
    "test_failed": "测试失败",

    # DFU Panel
    "dfu_upgrade": "固件升级",
    "dfu_warning_title": "⚠ 固件升级注意事项",
    "dfu_warning_1": "1. 升级过程中请勿断开电源或USB线",
    "dfu_warning_2": "2. 升级过程中请勿操作设备",
    "dfu_warning_3": "3. 升级完成后设备将自动重启",
    "device_type": "设备类型",
    "current_firmware": "当前固件",
    "firmware_type": "固件类型",
    "firmware_file": "固件文件",
    "btn_browse": "浏览...",
    "dfu_status_waiting": "等待开始",
    "dfu_status_idle": "状态: 空闲",
    "btn_start_upgrade": "🚀 开始升级",
    "btn_reset_state": "🔄 重置状态",
    "dfu_reset_tooltip": "如果DFU卡住显示'dfu is not available'，点击此按钮重置",
    "dfu_progress": "升级进度",
    "dfu_select_file": "请选择固件文件",
    "dfu_starting": "开始升级...",
    "dfu_completed": "升级完成",
    "dfu_failed": "升级失败",

    # Missing DFU keys
    "dfu_state_idle": "空闲",
    "dfu_state_starting": "启动中",
    "dfu_state_started": "已启动",
    "dfu_state_transferring": "传输中",
    "dfu_state_completed": "已完成",
    "dfu_state_aborted": "已中止",
    "dfu_success_reboot": "固件升级成功！设备将自动重启。",
    "dfu_aborted": "固件升级被中止",
    "dfu_timeout": "升级超时，状态: {state}",
    "dfu_fail_msg": "升级失败: {error}",
    "device_type_none": "设备类型: --",
    "current_firmware_none": "当前固件: --",
    "select_firmware_file_title": "选择固件文件",
    "error_no_device": "请先连接设备",
    "error_invalid_file": "请选择有效的固件文件",
    "dfu_confirm_title": "确认升级",
    "dfu_confirm_msg": "确定要开始固件升级吗？\n\n升级过程中请勿断开连接或关闭电源。",
    "dfu_upgrading": "正在升级...",
    "dfu_state_prefix": "状态: ",
    "dfu_upgrading_progress": "正在升级... {percent}%",
    "dfu_state_unknown": "未知({state})",
    "dfu_success_short": "✅ 升级成功，设备将自动重启",
    "dfu_failed_short": "❌ 升级失败",
    "dfu_reset_success_title": "成功",
    "dfu_reset_success_msg": "DFU状态已重置，可以重新开始升级",
    "dfu_reset_fail_msg": "重置失败: {error}",
    "dfu_state_reset": "状态已重置",

    "dfu_overlay_warning": "⚠ 固件升级中，请勿操作...",
    "dfu_status_warning": "⚠ DFU 升级中，请勿断开连接...",
    "dfu_wait_reconnect": "DFU 完成 - 等待设备重启后自动重连...",
    "status_connection_lost": "⚠ 连接丢失 - 设备可能已断开",
    "status_reconnecting": "正在重新连接设备...",

    # Action Sequence Panel
    "action_fist": "握拳",
    "action_open": "张开",
    "action_pinch_two": "两指捏",
    "action_pinch_three": "三指捏",
    "action_pinch_side": "侧捏",
    "action_point": "指向",
    "action_wave": "波浪",

    # Motor settings
    "turbo_mode": "Turbo模式",
    "enable_turbo": "启用Turbo模式",
    "turbo_interval": "间隔 (ms)",
    "turbo_duration": "持续时间 (ms)",
    "position_calibration": "位置校准",
    "auto_calibration": "开机自动校准",
    "manual_calibration": "手动校准",
    "force_level": "力度等级",
    "force_small": "小",
    "force_normal": "中",
    "force_full": "大",
    "unit_mode": "单位模式",
    "unit_normalized": "归一化 (0-1000)",
    "unit_physical": "物理单位 (度/mA)",
    "peripheral_settings": "外设设置",
    "led": "LED",
    "buzzer": "蜂鸣器",
    "vibration": "振动",
    "refresh_settings": "刷新设置",

    # Communication settings
    "modbus_baudrate": "Modbus/RS485 波特率",
    "canfd_baudrate": "CANFD 数据波特率",
    "current_settings": "当前设置",
    "confirm_baudrate_change": "确认波特率更改",
    "device_will_reboot": "更改后设备将重启。",

    # Finger settings (Revo2)
    "finger_settings": "手指设置 (Revo2)",
    "protected_currents": "保护电流 (Revo2)",
    "min_position": "最小位置",
    "max_position": "最大位置",
    "max_speed": "最大速度",
    "max_current": "最大电流",
    "protected_current": "保护电流",
    "apply": "应用",
    "apply_all": "全部应用",
    "finger_thumb_base": "拇指根部",
    "finger_thumb_aux": "拇指辅助",

    "v3_settings": "⚙ 设置",

    "v3_position_limits": "位置限制",
    "v3_speed_limits": "速度限制",
    "v3_joint_protect_current": "单关节保护电流",
    "v3_global_settings": "全局设置",
    "v3_global_protect_current": "全局保护电流",
    "v3_auto_refresh": "自动刷新 (3s)",
    "v3_read_parameters": "读取参数",
    "btn_apply": "应用",
    "btn_set": "设置",
    "v3_joint_pos_limits": "关节位置限制 (°)",
    "v3_joint_speed_limits": "关节速度限制 (rpm)",
    "v3_calibration_current": "校准电流 (A)",
    "v3_max_continuous_current": "最大持续电流 (A)",
    "v3_auto_calibration": "开机自动校准",
    "v3_manual_calibration": "🔧 手动校准",
    "v3_clear_errors": "🗑 清除电机错误",
    "btn_open": "张开",
    "btn_close": "闭合",
    "btn_run_finger": "▶ 运行手指",
    "v3_hw": "硬件版本",
    "v3_fw": "固件版本",
    "v3_sn": "设备序列号",
    "v3_online": "在线节点",
    "v3_offline": "离线节点",
    "v3_temp": "最高温度",
    "v3_errors": "故障节点",
    "v3_max_temp": "最高",
    "v3_overheat": "过热！",
    "v3_warm": "偏高",
    "v3_no_errors": "无错误",

    # Modes
    "mode_impedance": "阻抗",
    "mode_damping": "阻尼",
    "mode_mit": "MIT",
    "mode_trajectory": "轨迹规划",
    "communication": "通信设置",

    "system_state": "系统状态",
    "error_code": "错误码",
    "current_ma": "电流 (mA)",
    "voltage_v": "电压 (V)",
    "power_w": "功率 (W)",
    "temperature_c": "温度 (°C)",
    "motor_info": "马达信息",
    "motor_id": "马达 ID",
    "motor": "马达",

    "timing_step": "阶跃",

    # Touch Sensor Panel
    "touch_summary": "总览",
    "touch_palm": "手掌",
    "touch_thumb": "大拇指",
    "touch_index": "食指",
    "touch_middle": "中指",
    "touch_ring": "无名指",
    "touch_pinky": "小拇指",

    # Timing Test
    "timing_control": "控制",
    "timing_signal": "信号",
    "timing_sine": "正弦波",
    "timing_square": "方波",
    "timing_triangle": "三角波",

    # System Config
    "config_modbus": "Modbus",

    "v3_reset_finger_defaults": "↩ 恢复参数默认值",
    "v3_touch_screen": "触屏功能",
    "v3_teaching_mode": "🎓 示教模式",
    "v3_software_e_stop": "🛑 软件急停",
    "v3_use_broadcast_id": "使用广播ID",
    "v3_diagnostics": "📊 硬件诊断",
    "v3_diag_read": "读取信息",
    "v3_motor_status_info": "马达状态信息",

    # Teaching panel
    "teaching_mode": "示教模式",
    "teaching_controls": "控制",
    "teaching_record": "录制",
    "teaching_stop": "停止",
    "teaching_play": "回放",
    "teaching_save": "保存",
    "teaching_load": "加载",
    "teaching_save_title": "保存轨迹",
    "teaching_load_title": "加载轨迹",
    "teaching_record_freq": "录制频率:",
    "teaching_playback_speed": "速度:",
    "teaching_loop_count": "循环:",
    "teaching_status": "状态",
    "teaching_state_idle": "空闲",
    "teaching_state_recording": "录制中...",
    "teaching_state_playing": "回放中...",
    "teaching_trajectory_info": "轨迹信息",
}


# Global instance
_i18n = None


def get_i18n() -> I18n:
    """Get internationalization manager instance"""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n


def tr(key: str) -> str:
    """Translation shortcut function"""
    return get_i18n().translate(key)
