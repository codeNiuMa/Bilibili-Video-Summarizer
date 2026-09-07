"""Select a Qt binding whose plugins match the active Python environment."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _conda_qt_plugins() -> Path:
    return Path(sys.prefix) / "Library" / "lib" / "qt6" / "plugins"


_plugins = _conda_qt_plugins()
_use_conda_pyqt = (
    os.name == "nt"
    and _plugins.is_dir()
    and importlib.util.find_spec("PyQt6") is not None
)

if _use_conda_pyqt:
    os.environ["QT_PLUGIN_PATH"] = str(_plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(_plugins / "platforms")

    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal as Signal
    from PyQt6.QtGui import (
        QDesktopServices,
        QFont,
        QTextBlockFormat,
        QTextCursor,
        QTextDocument,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    QT_BINDING = "PyQt6"
else:
    os.environ.pop("QT_PLUGIN_PATH", None)
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtGui import (
        QDesktopServices,
        QFont,
        QTextBlockFormat,
        QTextCursor,
        QTextDocument,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    QT_BINDING = "PySide6"
