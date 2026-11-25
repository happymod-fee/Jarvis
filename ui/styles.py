"""
Advanced Futuristic Dark Glassmorphic Stylesheets for VAX PySide6 UI.
"""

DARK_THEME_QSS = """
/* Volume Slider */
QSlider#VolumeSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 0.10);
    border-radius: 2px;
}
QSlider#VolumeSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00d2ff, stop:1 #38bdf8);
    border-radius: 2px;
}
QSlider#VolumeSlider::handle:horizontal {
    background: #38bdf8;
    border: 2px solid #0ea5e9;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider#VolumeSlider::handle:horizontal:hover {
    background: #0ea5e9;
}

QWidget {
    font-family: 'Segoe UI', 'Nirmala UI', 'Inter', sans-serif;
    color: #f1f5f9;
    font-size: 13px;
}

#MainContainer {
    background-color: rgba(11, 16, 28, 245);
    border: 1px solid rgba(56, 189, 248, 0.30);
    border-radius: 20px;
}

QDialog, QWizard, QWizardPage {
    background-color: #0b101c;
    color: #f1f5f9;
}

#HeaderTitle {
    font-size: 14px;
    font-weight: 800;
    color: #38bdf8;
    letter-spacing: 1.4px;
}

#StatusLabel {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 10px;
    background-color: rgba(56, 189, 248, 0.14);
    border: 1px solid rgba(56, 189, 248, 0.35);
    color: #38bdf8;
}

#ModePillNormal {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 10px;
    background-color: rgba(16, 185, 129, 0.14);
    border: 1px solid rgba(16, 185, 129, 0.40);
    color: #34d399;
}
#ModePillNormal:hover {
    background-color: rgba(16, 185, 129, 0.25);
}

#ModePillTurbo {
    font-size: 10px;
    font-weight: 800;
    padding: 3px 10px;
    border-radius: 10px;
    background-color: rgba(245, 158, 11, 0.20);
    border: 1px solid rgba(251, 191, 36, 0.65);
    color: #fbbf24;
}
#ModePillTurbo:hover {
    background-color: rgba(245, 158, 11, 0.32);
}

#TranscriptArea {
    background-color: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 14px;
    padding: 10px;
    font-size: 13px;
    line-height: 1.45;
    color: #e2e8f0;
}

QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(56, 189, 248, 0.6);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: rgba(22, 31, 50, 0.9);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 10px;
    padding: 7px 11px;
    color: #f8fafc;
    selection-background-color: #0284c7;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
    background-color: rgba(26, 37, 60, 0.95);
}

#CommandInput {
    border-radius: 18px;
    padding: 8px 14px;
    font-size: 13px;
    background-color: rgba(22, 31, 50, 0.95);
    border: 1px solid rgba(56, 189, 248, 0.25);
}
#CommandInput:focus {
    border: 1px solid #38bdf8;
}

QPushButton {
    background-color: rgba(30, 41, 59, 0.85);
    border: 1px solid rgba(148, 163, 184, 0.20);
    border-radius: 10px;
    padding: 6px 12px;
    color: #f8fafc;
    font-weight: 600;
}

QPushButton:hover {
    background-color: rgba(56, 189, 248, 0.22);
    border: 1px solid rgba(56, 189, 248, 0.55);
}

QPushButton:pressed {
    background-color: rgba(56, 189, 248, 0.35);
}

#QuickChip {
    background-color: rgba(30, 41, 59, 0.65);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 12px;
    padding: 4px 9px;
    font-size: 11px;
    color: #cbd5e1;
}
#QuickChip:hover {
    background-color: rgba(56, 189, 248, 0.18);
    border: 1px solid rgba(56, 189, 248, 0.50);
    color: #ffffff;
}

#MicButton {
    background-color: rgba(16, 185, 129, 0.20);
    border: 1px solid rgba(16, 185, 129, 0.55);
    border-radius: 18px;
    color: #34d399;
    font-size: 14px;
}
#MicButton:hover {
    background-color: rgba(16, 185, 129, 0.35);
}

#SendButton {
    background-color: rgba(56, 189, 248, 0.22);
    border: 1px solid rgba(56, 189, 248, 0.55);
    border-radius: 18px;
    color: #38bdf8;
    font-size: 14px;
}
#SendButton:hover {
    background-color: rgba(56, 189, 248, 0.38);
}

#StopButton {
    background-color: rgba(239, 68, 68, 0.20);
    border: 1px solid rgba(239, 68, 68, 0.55);
    border-radius: 18px;
    color: #f87171;
    font-weight: 700;
    font-size: 11px;
}
#StopButton:hover {
    background-color: rgba(239, 68, 68, 0.42);
    color: #ffffff;
}

#IconButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px 6px;
    font-size: 13px;
}
#IconButton:hover {
    background-color: rgba(148, 163, 184, 0.15);
    border: 1px solid rgba(148, 163, 184, 0.25);
}

QTabWidget::pane {
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 10px;
    background-color: rgba(15, 23, 42, 0.65);
    top: -1px;
}

QTabBar::tab {
    background-color: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 4px;
    color: #94a3b8;
}

QTabBar::tab:selected {
    background-color: rgba(56, 189, 248, 0.2);
    border-bottom: 2px solid #38bdf8;
    color: #ffffff;
    font-weight: bold;
}

QTableWidget {
    background-color: rgba(15, 23, 42, 0.8);
    gridline-color: rgba(148, 163, 184, 0.15);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 8px;
}

QHeaderView::section {
    background-color: #161f33;
    color: #38bdf8;
    padding: 6px;
    border: none;
    font-weight: bold;
}
"""

