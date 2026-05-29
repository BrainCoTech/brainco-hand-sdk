"""Modern Connection Panel with Auto-Detection"""

import asyncio
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QPushButton, QLabel, QLineEdit,
    QFrame, QSizePolicy, QToolButton
)
from PySide6.QtCore import Signal, QThread, QObject, Qt

from .i18n import tr
from .styles import COLORS, CONNECTION_STATUS_STYLES

# Add parent directory to path for SDK import
sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk, get_protocol_display_name, int_to_baudrate, modbus_open

PROTO_AUTO = "auto"
PROTO_MODBUS = "modbus"
PROTO_PROTOBUF = "protobuf"
PROTO_CAN = "can"
PROTO_CANFD = "canfd"
PROTO_ETHERCAT = "ethercat"

PROTOCOL_LABELS = {
    PROTO_AUTO: "Auto Detect",
    PROTO_MODBUS: "Modbus/RS485",
    PROTO_PROTOBUF: "Protobuf",
    PROTO_CAN: "CAN 2.0",
    PROTO_CANFD: "CANFD",
    PROTO_ETHERCAT: "EtherCAT",
}


def protocol_key_to_label(protocol_key: str | None) -> str:
    return PROTOCOL_LABELS.get(protocol_key or "", protocol_key or "")


def protocol_label_to_key(protocol_label: str | None) -> str | None:
    if not protocol_label:
        return None
    for key, value in PROTOCOL_LABELS.items():
        if value == protocol_label:
            return key
    return None


def sdk_protocol_to_key(protocol_type):
    if sdk is None:
        return None
    if protocol_type == sdk.StarkProtocolType.Modbus:
        return PROTO_MODBUS
    if protocol_type == sdk.StarkProtocolType.Can:
        return PROTO_CAN
    if protocol_type == sdk.StarkProtocolType.CanFd:
        return PROTO_CANFD
    if protocol_type == sdk.StarkProtocolType.EtherCAT:
        return PROTO_ETHERCAT
    return None


def run_in_new_loop(async_factory):
    """Run a zero-arg async factory in a fresh event loop.

    The awaitable must be created after the loop is installed as current,
    otherwise PyO3 async wrappers may fail with "no running event loop".
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _runner():
            return await async_factory()

        return loop.run_until_complete(_runner())
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# Serial port listing
try:
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


def list_serial_ports():
    """List available serial ports"""
    if not HAS_SERIAL:
        return []
    import serial.tools.list_ports
    ports = []  # pyright: ignore[reportPossiblyUnboundVariable]
    for port in serial.tools.list_ports.comports():
        # Format: "COM3 - USB Serial Device" or "/dev/ttyUSB0 - CP2102"
        desc = f"{port.device}"
        if port.description and port.description != port.device:
            desc += f" - {port.description}"
        ports.append((port.device, desc))
    return ports


class AutoDetectWorker(QObject):
    """Auto-detection worker thread"""
    finished = Signal(object, int, object, str, str)  # ctx, slave_id, device_info, protocol_key, protocol_label
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, protocol=None, port=None, scan_all=False):
        super().__init__()
        self.protocol = protocol
        self.port = port
        self.scan_all = scan_all

    def run(self):
        """Execute auto-detection"""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            ctx, slave_id, device_info, protocol_key, protocol_label = loop.run_until_complete(
                self._auto_detect()
            )

            if ctx is None:
                self.error.emit("No devices found")
            else:
                self.finished.emit(ctx, slave_id, device_info, protocol_key, protocol_label)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _auto_detect(self):
        """Auto-detect device using unified API"""
        self.progress.emit("🔍 Scanning for devices...")

        # Use unified auto_detect API
        try:
            devices = await sdk.auto_detect(
                scan_all=self.scan_all,
                port=self.port,
                protocol=self.protocol
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

        if not devices:
            self.progress.emit("❌ No devices found")
            return None, 0, None, None, None

        device = devices[0]
        self.progress.emit(f"✅ Found {device.protocol_type} device")

        slave_id = device.slave_id

        # Use unified init_from_detected for all protocols
        ctx = await sdk.init_from_detected(device)

        # Build DeviceInfo from DetectedDevice (avoid re-querying get_device_info)
        # auto_detect already has correct hardware_type including TouchVendor resolution
        device_info = sdk.DeviceInfo(
            sku_type=device.sku_type if device.sku_type is not None else sdk.SkuType.MediumRight,
            hand_type=sdk.HandType.Right if (device.sku_type is None or device.sku_type in (sdk.SkuType.MediumRight, sdk.SkuType.SmallRight)) else sdk.HandType.Left,
            hardware_type=device.hardware_type if device.hardware_type is not None else sdk.StarkHardwareType.Revo2Basic,
            serial_number=device.serial_number or "",
            firmware_version=device.firmware_version or "",
            hardware_version=""
        )

        # Determine protocol name for display
        protocol_key = sdk_protocol_to_key(device.protocol_type)
        protocol_label = get_protocol_display_name(device.protocol_type)

        return ctx, slave_id, device_info, protocol_key, protocol_label

class ManualConnectWorker(QObject):
    """Manual connection worker thread"""
    finished = Signal(object, int, object, str, str)
    error = Signal(str)

    def __init__(self, protocol_key, params):
        super().__init__()
        self.protocol_key = protocol_key
        self.params = params

    def run(self):
        """Execute connection"""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            ctx, slave_id, device_info = loop.run_until_complete(self._connect())
            self.finished.emit(
                ctx,
                slave_id,
                device_info,
                self.protocol_key,
                protocol_key_to_label(self.protocol_key),
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _connect(self):
        """Connect to device"""
        if self.protocol_key == PROTO_MODBUS:
            ctx = await modbus_open(self.params['port'], int(self.params['baudrate']))
            slave_id = self.params['slave_id']
            device_info = await ctx.get_device_info(slave_id)
            return ctx, slave_id, device_info

        elif self.protocol_key == PROTO_PROTOBUF:
            # Protobuf uses fixed baudrate 115200
            ctx = await sdk.protobuf_open(self.params['port'], self.params['slave_id'])
            slave_id = self.params['slave_id']
            # Try to get device info from Protobuf device
            try:
                device_info = await ctx.get_device_info(slave_id)
            except Exception:
                # Fallback to minimal info if get_device_info fails
                device_info = sdk.DeviceInfo(
                    sku_type=sdk.SkuType.MediumRight,
                    hand_type=sdk.HandType.Right,
                    hardware_type=sdk.StarkHardwareType.Revo1Protobuf,
                    serial_number='',
                    firmware_version='',
                    hardware_version='',
                )
            return ctx, slave_id, device_info

        elif self.protocol_key == PROTO_CAN:
            port_name = self.params.get('port_name')
            if not port_name:
                devices = sdk.list_zqwl_devices()
                if not devices:
                    raise Exception("No ZQWL device found")
                port_name = devices[0].port_name

            sdk.init_zqwl_can(port_name, self.params.get('baudrate', 1000000))
            ctx = sdk.init_device_handler(sdk.StarkProtocolType.Can, master_id=1)
            slave_id = self.params.get('slave_id', 1)
            # IMPORTANT: Call get_device_info to auto-set hw_type (required for touch APIs)
            device_info = await ctx.get_device_info(slave_id)
            return ctx, slave_id, device_info

        elif self.protocol_key == PROTO_CANFD:
            port_name = self.params.get('port_name')
            if not port_name:
                devices = sdk.list_zqwl_devices()
                if not devices:
                    raise Exception("No ZQWL device found")
                port_name = devices[0].port_name

            sdk.init_zqwl_canfd(
                port_name,
                self.params.get('arb_baudrate', 1000000),
                self.params.get('data_baudrate', 5000000)
            )
            ctx = sdk.init_device_handler(sdk.StarkProtocolType.CanFd, master_id=1)
            slave_id = self.params.get('slave_id', 0x7F)
            # IMPORTANT: Call get_device_info to auto-set hw_type (required for touch APIs)
            device_info = await ctx.get_device_info(slave_id)
            return ctx, slave_id, device_info

        elif self.protocol_key == PROTO_ETHERCAT:
            master_pos = self.params.get('master_pos', 0)
            slave_pos = self.params.get('slave_pos', 0)

            ctx = sdk.init_device_handler(sdk.StarkProtocolType.EtherCAT, master_pos)
            await ctx.ec_setup_sdo(slave_pos)
            device_info = await ctx.get_device_info(slave_pos)

            # Reserve master and start PDO loop
            await ctx.ec_reserve_master()
            await ctx.ec_start_loop([slave_pos], 0, 1_000_000, 0, 0, 0)

            # For EtherCAT, slave_pos is used as slave_id
            return ctx, slave_pos, device_info

        else:
            raise ValueError(f"Unknown protocol: {self.protocol_key}")


class ConnectionPanel(QWidget):
    """Modern Connection Panel"""
    connected = Signal(object, int, object, str, str)
    about_to_disconnect = Signal()  # Emitted before closing device, so DataCollector can stop first
    disconnected = Signal()

    def __init__(self, mock_type=None):
        super().__init__()
        self.ctx = None
        self.slave_id = None
        self.protocol = None  # display label for compatibility
        self.protocol_key = None
        self.last_protocol = None  # display label for compatibility
        self.last_protocol_key = None
        self.last_slave_id = None
        self.worker = None
        self._thread: QThread | None = None
        self.mock_type = mock_type

        self._setup_ui()
        self.update_texts()

        if self.mock_type:
            # Bypass auto-detect and jump directly to mock connect
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._connect_mock)
            return

        # Auto-detect on startup
        if sdk and hasattr(sdk, 'auto_detect'):
            self._on_auto_detect()

    def _setup_ui(self):
        """Setup compact UI - single row layout"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Protocol selection
        self.proto_label = QLabel(tr("protocol") + ":")
        self.proto_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self.proto_label)

        self.protocol_combo = QComboBox()
        for protocol_key in [PROTO_AUTO, PROTO_MODBUS, PROTO_PROTOBUF, PROTO_CAN, PROTO_CANFD, PROTO_ETHERCAT]:
            self.protocol_combo.addItem(PROTOCOL_LABELS[protocol_key], protocol_key)
        if self.mock_type:
            self.proto_label.setVisible(False)
            self.protocol_combo.setVisible(False)
        self.protocol_combo.setMinimumWidth(120)
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_changed)
        layout.addWidget(self.protocol_combo)

        # Modbus parameters (hidden by default)
        self.modbus_frame = QWidget()
        modbus_layout = QHBoxLayout(self.modbus_frame)
        modbus_layout.setContentsMargins(0, 0, 0, 0)
        modbus_layout.setSpacing(8)

        self.modbus_port_label = QLabel(tr("port") + ":")
        modbus_layout.addWidget(self.modbus_port_label)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)
        self.port_combo.setEditable(True)  # Allow manual input if needed
        modbus_layout.addWidget(self.port_combo)

        # Refresh button for port list
        self.refresh_port_btn = QToolButton()
        self.refresh_port_btn.setText("🔄")
        self.refresh_port_btn.setToolTip("Refresh port list")
        self.refresh_port_btn.clicked.connect(self._refresh_port_list)
        modbus_layout.addWidget(self.refresh_port_btn)

        self.modbus_baud_label = QLabel(tr("baud") + ":")
        modbus_layout.addWidget(self.modbus_baud_label)
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(["115200", "460800", "921600", "1000000", "2000000", "3000000", "5000000"])
        self.baudrate_combo.setCurrentText("5000000")
        modbus_layout.addWidget(self.baudrate_combo)

        self.modbus_id_label = QLabel(tr("id") + ":")
        modbus_layout.addWidget(self.modbus_id_label)
        self.slave_id_spin = QSpinBox()
        self.slave_id_spin.setRange(1, 247)
        self.slave_id_spin.setValue(1)
        modbus_layout.addWidget(self.slave_id_spin)

        self.modbus_frame.setVisible(False)
        layout.addWidget(self.modbus_frame)

        # Protobuf parameters (hidden by default)
        self.protobuf_frame = QWidget()
        protobuf_layout = QHBoxLayout(self.protobuf_frame)
        protobuf_layout.setContentsMargins(0, 0, 0, 0)
        protobuf_layout.setSpacing(8)

        self.protobuf_port_label = QLabel(tr("port") + ":")
        protobuf_layout.addWidget(self.protobuf_port_label)
        self.protobuf_port_combo = QComboBox()
        self.protobuf_port_combo.setMinimumWidth(180)
        self.protobuf_port_combo.setEditable(True)
        protobuf_layout.addWidget(self.protobuf_port_combo)

        # Refresh button for port list
        self.refresh_protobuf_port_btn = QToolButton()
        self.refresh_protobuf_port_btn.setText("🔄")
        self.refresh_protobuf_port_btn.setToolTip("Refresh port list")
        self.refresh_protobuf_port_btn.clicked.connect(self._refresh_protobuf_port_list)
        protobuf_layout.addWidget(self.refresh_protobuf_port_btn)

        self.protobuf_id_label = QLabel(tr("id") + ":")
        protobuf_layout.addWidget(self.protobuf_id_label)
        self.protobuf_slave_spin = QSpinBox()
        self.protobuf_slave_spin.setRange(1, 247)
        self.protobuf_slave_spin.setValue(10)  # Default slave_id for Protobuf
        protobuf_layout.addWidget(self.protobuf_slave_spin)

        # Note: Protobuf uses fixed baudrate 115200
        self.protobuf_baud_label = QLabel("(115200 baud)")
        self.protobuf_baud_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        protobuf_layout.addWidget(self.protobuf_baud_label)

        self.protobuf_frame.setVisible(False)
        layout.addWidget(self.protobuf_frame)

        # CAN parameters (hidden by default)
        self.can_frame = QWidget()
        can_layout = QHBoxLayout(self.can_frame)
        can_layout.setContentsMargins(0, 0, 0, 0)
        can_layout.setSpacing(8)

        self.can_adapter_label = QLabel(tr("adapter") + ":")
        can_layout.addWidget(self.can_adapter_label)
        self.can_port_combo = QComboBox()
        self.can_port_combo.setMinimumWidth(150)
        can_layout.addWidget(self.can_port_combo)

        self.can_id_label = QLabel(tr("id") + ":")
        can_layout.addWidget(self.can_id_label)
        self.can_slave_spin = QSpinBox()
        self.can_slave_spin.setRange(1, 255)
        self.can_slave_spin.setValue(1)
        can_layout.addWidget(self.can_slave_spin)

        self.can_frame.setVisible(False)
        layout.addWidget(self.can_frame)

        # CANFD parameters (hidden by default)
        self.canfd_frame = QWidget()
        canfd_layout = QHBoxLayout(self.canfd_frame)
        canfd_layout.setContentsMargins(0, 0, 0, 0)
        canfd_layout.setSpacing(8)

        self.canfd_adapter_label = QLabel(tr("adapter") + ":")
        canfd_layout.addWidget(self.canfd_adapter_label)
        self.canfd_port_combo = QComboBox()
        self.canfd_port_combo.setMinimumWidth(150)
        canfd_layout.addWidget(self.canfd_port_combo)

        self.canfd_id_label = QLabel(tr("id") + ":")
        canfd_layout.addWidget(self.canfd_id_label)
        self.canfd_slave_spin = QSpinBox()
        self.canfd_slave_spin.setRange(1, 255)
        self.canfd_slave_spin.setValue(0x7E)
        canfd_layout.addWidget(self.canfd_slave_spin)

        self.canfd_frame.setVisible(False)
        layout.addWidget(self.canfd_frame)

        # EtherCAT parameters (hidden by default)
        self.ethercat_frame = QWidget()
        ec_layout = QHBoxLayout(self.ethercat_frame)
        ec_layout.setContentsMargins(0, 0, 0, 0)
        ec_layout.setSpacing(8)

        self.ec_master_label = QLabel("Master:")
        ec_layout.addWidget(self.ec_master_label)
        self.ec_master_spin = QSpinBox()
        self.ec_master_spin.setRange(0, 15)
        self.ec_master_spin.setValue(0)
        self.ec_master_spin.setToolTip("EtherCAT master position (usually 0)")
        ec_layout.addWidget(self.ec_master_spin)

        self.ec_slave_label = QLabel("Slave:")
        ec_layout.addWidget(self.ec_slave_label)
        self.ec_slave_spin = QSpinBox()
        self.ec_slave_spin.setRange(0, 255)
        self.ec_slave_spin.setValue(0)
        self.ec_slave_spin.setToolTip("EtherCAT slave position")
        ec_layout.addWidget(self.ec_slave_spin)

        self.ec_note_label = QLabel("(Linux only)")
        self.ec_note_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        ec_layout.addWidget(self.ec_note_label)

        self.ethercat_frame.setVisible(False)
        layout.addWidget(self.ethercat_frame)

        # Buttons
        self.auto_detect_btn = QPushButton(tr("btn_auto_detect"))
        self.auto_detect_btn.clicked.connect(self._on_auto_detect)
        self.auto_detect_btn.setMinimumHeight(36)
        layout.addWidget(self.auto_detect_btn)

        self.connect_btn = QPushButton(tr("btn_connect"))
        self.connect_btn.setProperty("class", "success")
        self.connect_btn.clicked.connect(self._on_connect)
        self.connect_btn.setMinimumHeight(36)
        self.connect_btn.setVisible(False)
        layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton(tr("btn_disconnect"))
        self.disconnect_btn.setProperty("class", "danger")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setMinimumHeight(36)
        layout.addWidget(self.disconnect_btn)
        
        if self.mock_type:
            self.auto_detect_btn.setVisible(False)
            self.connect_btn.setVisible(False)
            self.disconnect_btn.setVisible(False)

        # Status indicator
        self.status_indicator = QLabel("● " + tr("status_disconnected"))
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["disconnected"])
        layout.addWidget(self.status_indicator)

        # Device info (compact display)
        self.info_labels = {}

        self.info_labels["hardware"] = QLabel("—")
        self.info_labels["hardware"].setStyleSheet(f"color: {COLORS['text_primary']};")
        layout.addWidget(self.info_labels["hardware"])

        # Hidden labels for compatibility
        self.info_labels["serial"] = QLabel("")
        self.info_labels["protocol"] = QLabel("")
        self.info_labels["port"] = QLabel("")
        self.info_labels["slave_id"] = QLabel("")
        self.info_labels["firmware"] = QLabel("")

        # Status message (hidden, for error display)
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Refresh ZQWL devices
        self._refresh_zqwl_devices()

    def _refresh_zqwl_devices(self):
        """Refresh ZQWL device list"""
        if sdk is None:
            return

        try:
            devices = sdk.list_zqwl_devices()

            self.can_port_combo.clear()
            self.canfd_port_combo.clear()

            for d in devices:
                label = f"{d.port_name}"
                self.can_port_combo.addItem(label, d.port_name)
                if d.supports_canfd:
                    self.canfd_port_combo.addItem(label, d.port_name)
        except Exception as e:
            print(f"Error refreshing ZQWL devices: {e}")

    def update_texts(self):
        """Update texts for i18n"""
        self.proto_label.setText(tr("protocol") + ":")
        self.modbus_port_label.setText(tr("port") + ":")
        self.modbus_baud_label.setText(tr("baud") + ":")
        self.modbus_id_label.setText(tr("id") + ":")
        self.protobuf_port_label.setText(tr("port") + ":")
        self.protobuf_id_label.setText(tr("id") + ":")
        self.can_adapter_label.setText(tr("adapter") + ":")
        self.can_id_label.setText(tr("id") + ":")
        self.canfd_adapter_label.setText(tr("adapter") + ":")
        self.canfd_id_label.setText(tr("id") + ":")
        self.ec_master_label.setText("Master:")
        self.ec_slave_label.setText("Slave:")
        self.auto_detect_btn.setText(tr("btn_auto_detect"))
        self.connect_btn.setText(tr("btn_connect"))
        self.disconnect_btn.setText(tr("btn_disconnect"))
        # Update status indicator based on current state
        if self.ctx:
            self.status_indicator.setText("● " + tr("status_connected"))
        else:
            self.status_indicator.setText("● " + tr("status_disconnected"))

    def _on_protocol_changed(self, protocol_label):
        """Protocol selection changed"""
        protocol_key = self.protocol_combo.currentData()
        self.modbus_frame.setVisible(protocol_key == PROTO_MODBUS)
        self.protobuf_frame.setVisible(protocol_key == PROTO_PROTOBUF)
        self.can_frame.setVisible(protocol_key == PROTO_CAN)
        self.canfd_frame.setVisible(protocol_key == PROTO_CANFD)
        self.ethercat_frame.setVisible(protocol_key == PROTO_ETHERCAT)
        self.connect_btn.setVisible(protocol_key != PROTO_AUTO)
        self.auto_detect_btn.setVisible(protocol_key == PROTO_AUTO)

        # Refresh port list when switching to Modbus or Protobuf
        if protocol_key == PROTO_MODBUS:
            self._refresh_port_list()
        elif protocol_key == PROTO_PROTOBUF:
            self._refresh_protobuf_port_list()

    def _refresh_port_list(self):
        """Refresh serial port list"""
        current = self.port_combo.currentText()
        self.port_combo.clear()

        ports = list_serial_ports()
        if ports:
            for device, desc in ports:
                self.port_combo.addItem(desc, device)
            # Try to restore previous selection
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == current or current in self.port_combo.itemText(i):
                    self.port_combo.setCurrentIndex(i)
                    break
        else:
            # No ports found, add placeholder
            self.port_combo.addItem("No ports found", "")

    def _refresh_protobuf_port_list(self):
        """Refresh serial port list for Protobuf"""
        current = self.protobuf_port_combo.currentText()
        self.protobuf_port_combo.clear()

        ports = list_serial_ports()
        if ports:
            for device, desc in ports:
                self.protobuf_port_combo.addItem(desc, device)
            # Try to restore previous selection
            for i in range(self.protobuf_port_combo.count()):
                if self.protobuf_port_combo.itemData(i) == current or current in self.protobuf_port_combo.itemText(i):
                    self.protobuf_port_combo.setCurrentIndex(i)
                    break
        else:
            # No ports found, add placeholder
            self.protobuf_port_combo.addItem("No ports found", "")

    def _on_auto_detect(self):
        """Start auto-detection"""
        if sdk is None:
            self.status_label.setText("❌ SDK not installed")
            return

        self._set_connecting_state()
        self.status_label.setText("🔍 Scanning for devices...")

        self._thread = QThread()
        self.worker = AutoDetectWorker()
        self.worker.moveToThread(self._thread)

        self._thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_connect_success)
        self.worker.error.connect(self._on_connect_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._thread.quit)
        self.worker.error.connect(self._thread.quit)

        self._thread.start()

    def _on_connect(self):
        """Manual connect"""
        if sdk is None:
            self.status_label.setText("❌ SDK not installed")
            return

        protocol_key = self.protocol_combo.currentData()

        if protocol_key == PROTO_AUTO:
            self._on_auto_detect()
            return

        if protocol_key == PROTO_MODBUS:
            # Get port from combo (use itemData for actual device path)
            port = self.port_combo.currentData()
            if not port:
                port = self.port_combo.currentText()  # Fallback to text if manually entered
            params = {
                'port': port,
                'baudrate': self.baudrate_combo.currentText(),
                'slave_id': self.slave_id_spin.value()
            }
        elif protocol_key == PROTO_PROTOBUF:
            # Get port from combo
            port = self.protobuf_port_combo.currentData()
            if not port:
                port = self.protobuf_port_combo.currentText()
            params = {
                'port': port,
                'slave_id': self.protobuf_slave_spin.value()
            }
        elif protocol_key == PROTO_CAN:
            idx = self.can_port_combo.currentIndex()
            params = {
                'port_name': self.can_port_combo.itemData(idx) if idx >= 0 else None,
                'slave_id': self.can_slave_spin.value(),
                'baudrate': 1000000
            }
        elif protocol_key == PROTO_CANFD:
            idx = self.canfd_port_combo.currentIndex()
            params = {
                'port_name': self.canfd_port_combo.itemData(idx) if idx >= 0 else None,
                'slave_id': self.canfd_slave_spin.value(),
                'arb_baudrate': 1000000,
                'data_baudrate': 5000000
            }
        elif protocol_key == PROTO_ETHERCAT:
            params = {
                'master_pos': self.ec_master_spin.value(),
                'slave_pos': self.ec_slave_spin.value(),
            }
        else:
            self.status_label.setText(f"❌ Unknown protocol: {protocol_key}")
            return

        self._set_connecting_state()
        self._start_manual_connect(protocol_key, params, "Connecting...")

    def _start_manual_connect(self, protocol_key, params, status_text):
        """Start a manual connection worker with explicit protocol parameters."""
        self.status_label.setText(status_text)

        self._thread = QThread()
        self.worker = ManualConnectWorker(protocol_key, params)
        self.worker.moveToThread(self._thread)

        self._thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_connect_success)
        self.worker.error.connect(self._on_connect_error)
        self.worker.finished.connect(self._thread.quit)
        self.worker.error.connect(self._thread.quit)

        self._thread.start()

    def reconnect_last_device(self):
        """Reconnect using the last successful protocol when possible."""
        protocol = self.last_protocol_key
        slave_id = self.last_slave_id

        if sdk is None or protocol is None:
            self._on_auto_detect()
            return

        if protocol == PROTO_CANFD:
            self._refresh_zqwl_devices()
            idx = self.canfd_port_combo.currentIndex()
            params = {
                'port_name': self.canfd_port_combo.itemData(idx) if idx >= 0 else None,
                'slave_id': slave_id if slave_id is not None else self.canfd_slave_spin.value(),
                'arb_baudrate': 1000000,
                'data_baudrate': 5000000
            }
            self._set_connecting_state()
            self._start_manual_connect(protocol, params, "Reconnecting CANFD...")
            return

        if protocol == PROTO_CAN:
            self._refresh_zqwl_devices()
            idx = self.can_port_combo.currentIndex()
            params = {
                'port_name': self.can_port_combo.itemData(idx) if idx >= 0 else None,
                'slave_id': slave_id if slave_id is not None else self.can_slave_spin.value(),
                'baudrate': 1000000
            }
            self._set_connecting_state()
            self._start_manual_connect(protocol, params, "Reconnecting CAN 2.0...")
            return

        self._on_auto_detect()

    def _set_connecting_state(self):
        """Set UI to connecting state"""
        self.auto_detect_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.status_indicator.setText("● Connecting...")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["connecting"])

    def _on_progress(self, message):
        """Progress update"""
        self.status_label.setText(message)

    def _on_connect_success(self, ctx, slave_id, device_info, protocol_key, protocol_label):
        """Connection successful"""
        self.ctx = ctx
        self.slave_id = slave_id
        self.protocol_key = protocol_key
        self.protocol = protocol_label
        self.last_protocol_key = protocol_key
        self.last_protocol = protocol_label
        self.last_slave_id = slave_id

        # Update UI state
        self.auto_detect_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)

        self.status_indicator.setText("● Connected")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["connected"])

        # Update device info (compact display - hardware type only)
        if device_info:
            hw_type = str(device_info.hardware_type).replace("StarkHardwareType.", "")
            self.info_labels["hardware"].setText(hw_type)
            self.info_labels["serial"].setText(device_info.serial_number)  # Keep for internal use
            self.info_labels["firmware"].setText(device_info.firmware_version)

        self.connected.emit(ctx, slave_id, device_info, protocol_key, protocol_label)

    def _on_connect_error(self, error):
        """Connection failed"""
        self.auto_detect_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)

        self.status_indicator.setText("● Error")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["error"])
        self.status_label.setText(f"❌ {error}")

    def _on_disconnect(self):
        """Disconnect"""
        if self.ctx:
            # Signal MainWindow to stop DataCollector BEFORE closing serial port
            # (DataCollector holds Arc ref to ctx and actively reads from serial port)
            self.about_to_disconnect.emit()

            try:
                protocol = self.protocol_key or ""

                if protocol == PROTO_ETHERCAT:
                    async def close_ethercat():
                        await self.ctx.ec_stop_loop()
                        await self.ctx.close()
                    run_in_new_loop(close_ethercat)
                elif protocol in [PROTO_CAN, PROTO_CANFD]:
                    if hasattr(sdk, 'close_device_handler'):
                        run_in_new_loop(lambda: sdk.close_device_handler(self.ctx))
                    else:
                        # Fallback for older SDK versions
                        sdk.close_zqwl()
                elif protocol == PROTO_MODBUS:
                    if hasattr(sdk, 'modbus_close'):
                        run_in_new_loop(lambda: sdk.modbus_close(self.ctx))
                    else:
                        run_in_new_loop(lambda: self.ctx.close())
                elif protocol == PROTO_PROTOBUF:
                    run_in_new_loop(lambda: self.ctx.close())
                elif hasattr(sdk, 'close_device_handler'):
                    run_in_new_loop(lambda: sdk.close_device_handler(self.ctx))
                else:
                    run_in_new_loop(lambda: self.ctx.close())
            except Exception as e:
                print(f"Error closing device: {e}")

        self.ctx = None
        self.slave_id = None
        self.protocol = None
        self.protocol_key = None

        # Reset UI
        self.auto_detect_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

        self.status_indicator.setText("● Disconnected")
        self.status_indicator.setStyleSheet(CONNECTION_STATUS_STYLES["disconnected"])

        # Clear device info
        self.info_labels["hardware"].setText("—")
        self.info_labels["serial"].setText("")

        self.status_label.setText("")
        self.disconnected.emit()

    def _connect_mock(self):
        """Connect to mock device for UI debugging"""
        from .mock_device import MockDeviceContext
        hw_type = sdk.StarkHardwareType.Revo2Basic
        
        m_type = self.mock_type.lower()
        if m_type == "revo1":
            hw_type = sdk.StarkHardwareType.Revo1Basic
        elif m_type == "revo1-touch":
            hw_type = sdk.StarkHardwareType.Revo1Touch
        elif m_type == "revo2":
            hw_type = sdk.StarkHardwareType.Revo2Basic
        elif m_type == "revo2-touch":
            hw_type = sdk.StarkHardwareType.Revo2Touch
        elif m_type == "revo2-pressure":
            hw_type = sdk.StarkHardwareType.Revo2TouchPressure
        elif m_type == "revo2-force3d":
            hw_type = sdk.StarkHardwareType.Revo2TouchForce3D
            
        ctx = MockDeviceContext(hw_type)
        slave_id = 1
        protocol = f"Mock ({self.mock_type})"
        
        # We must create device_info to pass to the success callback
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            device_info = loop.run_until_complete(ctx.get_device_info(slave_id))
        finally:
            loop.close()
            
        self._on_connect_success(ctx, slave_id, device_info, "mock", protocol)
