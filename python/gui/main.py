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
    
    # Dark theme has compatibility issues on macOS, use system default
    # app.setStyleSheet(DARK_THEME)
    
    # Create and show main window
    window = MainWindow(mock_type=args.mock)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
