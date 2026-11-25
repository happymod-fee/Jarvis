"""
Pro-Grade Futuristic Dark Glassmorphic Stylesheets for VAX / Jarvis PySide6 UI.
Designed for crisp legibility in Bangla, Banglish, and English with subtle cyan/emerald accents.
"""

DARK_THEME_QSS = """
QWidget {
    font-family: 'Segoe UI', 'Nirmala UI', 'Inter', sans-serif;
    color: #f1f5f9;
    font-size: 13px;
}

#MainContainer {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(13, 19, 36, 248),
        stop:0.55 rgba(10, 15, 28, 248),
        stop:1 rgba(7, 11, 21, 250));
    border: 1px solid rgba(56, 189, 248, 0.34);
    border-radius: 22px;
}

#HeaderDivider {
    background-color: rgba(148, 163, 184, 0.12);
    max-height: 1px;
    min-height: 1px;
}

#ControlStrip {
    background-color: rgba(18, 26, 46, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 12px;
}

QDialog, QWizard, QWizardPage {
    background-color: #090e1a;
    color: #f1f5f9;
}

#HeaderTitle {
    font-size: 13px;
    font-weight: 800;
    color: #e0f2fe;
    letter-spacing: 1.2px;
}

#StatusLabel {
    font-size: 9px;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 9px;
    background-color: rgba(56, 189, 248, 0.14);
    border: 1px solid rgba(56, 189, 248, 0.38);
    color: #38bdf8;
    letter-spacing: 0.6px;
}

#ModePillNormal {
    font-size: 9px;
    font-weight: 800;
    padding: 3px 9px;
    border-radius: 9px;
    background-color: rgba(16, 185, 129, 0.14);
    border: 1px solid rgba(16, 185, 129, 0.42);
    color: #34d399;
}
#ModePillNormal:hover {
    background-color: rgba(16, 185, 129, 0.28);
}

#ModePillTurbo {
    font-size: 9px;
    font-weight: 800;
    padding: 3px 9px;
    border-radius: 9px;
    background-color: rgba(245, 158, 11, 0.22);
    border: 1px solid rgba(251, 191, 36, 0.75);
    color: #fbbf24;
}
#ModePillTurbo:hover {
    background-color: rgba(245, 158, 11, 0.35);
}

#TranscriptArea {
    background-color: rgba(13, 20, 38, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 15px;
    padding: 10px;
    font-size: 12.5px;
    line-height: 1.48;
    color: #e2e8f0;
}

QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: rgba(148, 163, 184, 0.28);
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(56, 189, 248, 0.65);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Volume Slider */
QSlider#VolumeSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 0.12);
    border-radius: 2px;
}
QSlider#VolumeSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0ea5e9, stop:1 #38bdf8);
    border-radius: 2px;
}
QSlider#VolumeSlider::handle:horizontal {
    background: #e0f2fe;
    border: 2px solid #38bdf8;
    width: 11px;
    height: 11px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider#VolumeSlider::handle:horizontal:hover {
    background: #ffffff;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: rgba(20, 29, 49, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 10px;
    padding: 7px 11px;
    color: #f8fafc;
    selection-background-color: #0284c7;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
    background-color: rgba(24, 35, 58, 0.96);
}

#CommandInput {
    border-radius: 18px;
    padding: 8px 14px;
    font-size: 13px;
    background-color: rgba(19, 28, 48, 0.96);
    border: 1px solid rgba(56, 189, 248, 0.28);
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
    background-color: rgba(25, 35, 58, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 11px;
    padding: 5px 8px;
    font-size: 10.5px;
    color: #cbd5e1;
}
#QuickChip:hover {
    background-color: rgba(56, 189, 248, 0.20);
    border: 1px solid rgba(56, 189, 248, 0.55);
    color: #ffffff;
}

#MicButton {
    background-color: rgba(16, 185, 129, 0.20);
    border: 1px solid rgba(16, 185, 129, 0.60);
    border-radius: 18px;
    color: #34d399;
    font-size: 14px;
}
#MicButton:hover {
    background-color: rgba(16, 185, 129, 0.36);
}

#SendButton {
    background-color: rgba(56, 189, 248, 0.22);
    border: 1px solid rgba(56, 189, 248, 0.58);
    border-radius: 18px;
    color: #38bdf8;
    font-size: 14px;
}
#SendButton:hover {
    background-color: rgba(56, 189, 248, 0.40);
}

#StopButton {
    background-color: rgba(239, 68, 68, 0.20);
    border: 1px solid rgba(239, 68, 68, 0.58);
    border-radius: 18px;
    color: #f87171;
    font-weight: 800;
    font-size: 10.5px;
    letter-spacing: 0.5px;
}
#StopButton:hover {
    background-color: rgba(239, 68, 68, 0.44);
    color: #ffffff;
}

#IconButton {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(148, 163, 184, 0.10);
    border-radius: 8px;
    padding: 3px;
    font-size: 12px;
}
#IconButton:hover {
    background-color: rgba(56, 189, 248, 0.16);
    border: 1px solid rgba(56, 189, 248, 0.35);
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
"""
