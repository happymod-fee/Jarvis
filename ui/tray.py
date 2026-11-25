"""
System Tray Integration for VAX.
Provides background system tray icon, context menu, and Windows startup management.
Uses modern PySide6 scoped enums and protected signal emissions.
"""

import sys
import winreg
import logging
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from vax.config import config_manager

logger = logging.getLogger("VAX.UI.Tray")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "VAXVoiceAssistant"


def create_tray_pixmap() -> QPixmap:
    """Generates a clean programmatic tray icon pixmap."""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Cyan gradient circle
    painter.setBrush(QColor(0, 210, 255))
    painter.setPen(QColor(255, 255, 255, 200))
    painter.drawEllipse(4, 4, 56, 56)

    # Stylized 'V' letter
    painter.setPen(QColor(10, 15, 25))
    font = QFont("Segoe UI", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "V")
    painter.end()

    return pix


def set_windows_startup(enabled: bool) -> bool:
    """Configures whether VAX launches automatically on Windows login."""
    if sys.platform != "win32":
        return False

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe_path = sys.executable
            if not getattr(sys, "frozen", False):
                main_py = Path(__file__).resolve().parent.parent / "main.py"
                cmd = f'"{exe_path}" "{main_py}"'
            else:
                cmd = f'"{exe_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            logger.info("Enabled launch on Windows startup: %s", cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                logger.info("Disabled launch on Windows startup.")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error("Failed to update Windows startup registry: %s", e)
        return False


class TrayIconManager(QObject):
    """
    Manages the system tray icon, notifications, and menu actions.
    """
    show_window_requested = Signal()
    settings_requested = Signal()
    logs_requested = Signal()
    toggle_listening_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(parent)
        self.pixmap = create_tray_pixmap()
        self.icon = QIcon(self.pixmap)
        self.tray_icon.setIcon(self.icon)
        self.tray_icon.setToolTip("VAX Voice Assistant")

        self._setup_menu()
        self.tray_icon.activated.connect(self._on_activated)
        self.tray_icon.show()

    def _setup_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #161b2c;
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #00d2ff;
                color: #050b14;
            }
        """)

        # Title Item
        header = menu.addAction("🤖 VAX Voice Assistant")
        header.setEnabled(False)
        menu.addSeparator()

        self.action_toggle = menu.addAction("🎙️ Voice: Active")
        self.action_toggle.triggered.connect(self._safe_toggle_listening)

        action_show = menu.addAction("🪟 Show Assistant Window")
        action_show.triggered.connect(self._safe_show_window)

        action_logs = menu.addAction("📋 Action History")
        action_logs.triggered.connect(self._safe_show_logs)

        action_settings = menu.addAction("⚙️ Settings")
        action_settings.triggered.connect(self._safe_show_settings)

        menu.addSeparator()

        # Startup checkbox
        self.action_startup = menu.addAction("🚀 Start with Windows")
        self.action_startup.setCheckable(True)
        is_startup = config_manager.get("general", "start_with_windows", False)
        self.action_startup.setChecked(is_startup)
        self.action_startup.triggered.connect(self._on_startup_toggled)

        menu.addSeparator()

        action_quit = menu.addAction("❌ Quit VAX")
        action_quit.triggered.connect(self._safe_quit)

        self.tray_icon.setContextMenu(menu)

    def _safe_toggle_listening(self):
        try:
            self.toggle_listening_requested.emit()
        except Exception as e:
            logger.error("Error toggling listening: %s", e)

    def _safe_show_window(self):
        try:
            self.show_window_requested.emit()
        except Exception as e:
            logger.error("Error showing window: %s", e)

    def _safe_show_logs(self):
        try:
            self.logs_requested.emit()
        except Exception as e:
            logger.error("Error showing logs: %s", e)

    def _safe_show_settings(self):
        try:
            self.settings_requested.emit()
        except Exception as e:
            logger.error("Error showing settings: %s", e)

    def _safe_quit(self):
        try:
            self.quit_requested.emit()
        except Exception as e:
            logger.error("Error quitting application: %s", e)

    def _on_startup_toggled(self, checked: bool):
        try:
            config_manager.set("general", "start_with_windows", checked)
            set_windows_startup(checked)
        except Exception as e:
            logger.error("Error updating startup setting: %s", e)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single left click
            self._safe_show_window()

    def set_listening_status(self, is_active: bool):
        """Alias used by main.py on_toggle_listening to update tray menu text."""
        self.update_listening_status(is_active)

    def update_listening_status(self, is_active: bool):
        try:
            if is_active:
                self.action_toggle.setText("🎙️ Voice: Active (Listening)")
            else:
                self.action_toggle.setText("⏸️ Voice: Paused")
        except Exception as e:
            logger.debug("Error updating tray status text: %s", e)

    def show_notification(self, title: str, message: str):
        try:
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        except Exception as e:
            logger.debug("Error displaying tray notification: %s", e)
