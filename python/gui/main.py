#!/usr/bin/env python3
"""
Stark SDK GUI - Modern Control Interface
Supports Revo1/Revo2 protocols and device types

Usage:
    python main.py                                # Auto-detect
"""

import argparse
import signal
import sys
from pathlib import Path

# Suppress pyqtgraph disconnect warnings (PySide6 compatibility issue)
import warnings
warnings.filterwarnings("ignore", message="Failed to disconnect.*", category=RuntimeWarning)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPalette, QColor

from gui.main_window import MainWindow
from gui.styles import DARK_THEME


def main():
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Stark SDK GUI")
    parser.add_argument("--mock", nargs="?", const="revo2", default=None,
                        help="Run in mock mode for UI testing. Options: revo2, revo2-touch, etc. Default: revo2")
    args = parser.parse_args()



    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Stark SDK")
    app.setOrganizationName("BrainCo")
    app.setApplicationVersion("1.0.7")
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Dynamic Light / Dark System-Adaptive Theme Engine
    app.setStyle("Fusion")
    
    def apply_theme(app_instance, scheme_name):
        """Applies distinct premium palette and stylesheet based on theme scheme_name ('dark' or 'light')"""
        if scheme_name == "dark":
            # --- Premium Dark Theme ---
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor("#1a1a2e"))
            dark_palette.setColor(QPalette.WindowText, QColor("#ecf0f1"))
            dark_palette.setColor(QPalette.Base, QColor("#1e2633"))
            dark_palette.setColor(QPalette.AlternateBase, QColor("#16213e"))
            dark_palette.setColor(QPalette.ToolTipBase, QColor("#3d4a5c"))
            dark_palette.setColor(QPalette.ToolTipText, QColor("#ecf0f1"))
            dark_palette.setColor(QPalette.Text, QColor("#ecf0f1"))
            dark_palette.setColor(QPalette.Button, QColor("#3498db"))
            dark_palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
            dark_palette.setColor(QPalette.BrightText, QColor("#e74c3c"))
            dark_palette.setColor(QPalette.Link, QColor("#3498db"))
            dark_palette.setColor(QPalette.Highlight, QColor("#3498db"))
            dark_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            app_instance.setPalette(dark_palette)
            app_instance.setStyleSheet(DARK_THEME)
        else:
            # --- Premium Light Theme ---
            light_palette = QPalette()
            light_palette.setColor(QPalette.Window, QColor("#f5f5f7"))
            light_palette.setColor(QPalette.WindowText, QColor("#1d1d1f"))
            light_palette.setColor(QPalette.Base, QColor("#ffffff"))
            light_palette.setColor(QPalette.AlternateBase, QColor("#e5e5ea"))
            light_palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
            light_palette.setColor(QPalette.ToolTipText, QColor("#1d1d1f"))
            light_palette.setColor(QPalette.Text, QColor("#1d1d1f"))
            light_palette.setColor(QPalette.Button, QColor("#007aff"))
            light_palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
            light_palette.setColor(QPalette.BrightText, QColor("#ff3b30"))
            light_palette.setColor(QPalette.Link, QColor("#007aff"))
            light_palette.setColor(QPalette.Highlight, QColor("#007aff"))
            light_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            app_instance.setPalette(light_palette)
            
            # Premium macOS-like Light Stylesheet for high contrast and readability
            light_theme = """
            QMainWindow {
                background-color: #f5f5f7;
            }
            QWidget {
                color: #1d1d1f;
                font-size: 13px;
            }
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 12px;
                margin-top: 16px;
                padding: 16px;
                font-weight: 600;
                color: #1d1d1f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 0 8px;
                background-color: #ffffff;
                color: #1d1d1f;
            }
            QGroupBox QLabel {
                color: #1d1d1f;
            }
            QTabWidget::pane {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 12px;
                padding: 8px;
            }
            QTabBar::tab {
                background-color: #e5e5ea;
                color: #8e8e93;
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border: 1px solid #d2d2d7;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1d1d1f;
                border-bottom: 2px solid #007aff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #d1d1d6;
            }
            QPushButton {
                background-color: #007aff;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: 600;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #148cff;
            }
            QPushButton:pressed {
                background-color: #0062cc;
            }
            QPushButton[class="secondary"] {
                background-color: #e5e5ea;
                color: #1d1d1f;
            }
            QPushButton[class="secondary"]:hover {
                background-color: #d1d1d6;
            }
            QComboBox {
                background-color: #ffffff;
                color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QSlider::groove:horizontal {
                background-color: #d1d1d6;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background-color: #007aff;
                width: 20px;
                height: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }
            QSlider::sub-page:horizontal {
                background-color: #007aff;
                border-radius: 4px;
            }
            QLabel {
                color: #1d1d1f;
            }
            """
            app_instance.setStyleSheet(light_theme)

    # Detect current color scheme with multi-version fallback (avoids AttributeError on older Qt)
    current_scheme = "light"
    color_scheme_class = getattr(Qt, "ColorScheme", None)
    
    if color_scheme_class is not None:
        try:
            qt_scheme = app.styleHints().colorScheme()
            if qt_scheme == color_scheme_class.Dark:
                current_scheme = "dark"
        except Exception:
            pass
    else:
        # Fallback to macOS plist detection if older PySide6 version lacks Qt.ColorScheme
        try:
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=1.0)
            if "Dark" in out.stdout:
                current_scheme = "dark"
        except Exception:
            pass

    # Initial theme application
    apply_theme(app, current_scheme)

    # Subscribe to dynamic macOS system theme switches in real-time if supported
    if color_scheme_class is not None:
        try:
            app.styleHints().colorSchemeChanged.connect(
                lambda scheme: apply_theme(app, "dark" if scheme == color_scheme_class.Dark else "light")
            )
        except Exception:
            pass
    
    # Create and show main window
    window = MainWindow(mock_type=args.mock)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
