"""
Advanced Floating HUD for VAX Voice Assistant.

LAYOUT (top to bottom):
  ┌──────────────────────────────────────────────────────────┐
  │  🤖 VAX AI   [READY] [🛡️NORMAL] ─── [🔇][📋][⚙️][─]  │  <- Header
  ├──────────────────────────────────────────────────────────┤
  │            🎙️ Mic Active: Headset T-43 ·  🔈──●──  🔊  │  <- Mic + Volume bar
  ├──────────────────────────────────────────────────────────┤
  │                   [ Animated Orb ]                       │  <- Voice Orb
  │          Listening... speak in Bangla or English         │  <- Status text
  ├──────────────────────────────────────────────────────────┤
  │  [🎵 Song]  [🌤️ Weather]  [🖥️ PC]  [🌐 Chrome]  [🧠]  │  <- Quick chips + Memory
  ├──────────────────────────────────────────────────────────┤
  │   ┌──────────────────────────────────────────────────┐   │
  │   │  🤖 VAX: Hi! What can I help you with?          │   │  <- Transcript
  │   │  You: Chrome open koro                           │   │
  │   └──────────────────────────────────────────────────┘   │
  ├──────────────────────────────────────────────────────────┤
  │  [input text field............]  [🎙️]  [➤]  [STOP]      │  <- Input dock
  └──────────────────────────────────────────────────────────┘

New controls added:
  - 🔇 Mic mute/unmute toggle button in header (default: unmuted)
  - 🔈🔊 Volume quick-slider in mic-status row
  - 🧠 Memory facts chip — opens inline memory popup in transcript
  - Resizable window (minimum 380x540, default 420x600)
  - Volume slider wired to tts_engine.set_volume (0–100)
"""

import math
import html
import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPoint, Signal, QSize
from PySide6.QtGui import (
    QPainter,
    QColor,
    QRadialGradient,
    QPen,
    QBrush,
    QTextCursor,
    QGuiApplication,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QGraphicsDropShadowEffect,
    QSlider,
    QSizeGrip,
)

from vax.config import config_manager
from vax.ui.styles import DARK_THEME_QSS

logger = logging.getLogger("VAX.UI.MiniWindow")


# ---------------------------------------------------------------------------
# Voice Orb Widget
# ---------------------------------------------------------------------------
class VoiceOrbWidget(QWidget):
    """
    Multi-ring animated HUD Orb. States:
      IDLE      – cyan breathing
      LISTENING – emerald ripple waves
      THINKING  – amber dual-orbit arcs
      SPEAKING  – violet resonance rings
      NO_MIC    – red standby
      MUTED     – grey static (mic muted by user)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(116, 116)
        self.state = "IDLE"
        self.phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_animation)
        self.timer.start(33)  # ~30fps

    def set_state(self, new_state: str):
        try:
            self.state = new_state.upper()
            self.update()
        except Exception as e:
            logger.debug("Error setting orb state: %s", e)

    def _update_animation(self):
        try:
            self.phase += 0.08
            if self.phase > 200 * math.pi:
                self.phase -= 200 * math.pi
            self.update()
        except Exception as e:
            logger.debug("Error in orb animation: %s", e)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cx, cy = self.width() / 2.0, self.height() / 2.0
            base_r = 25.0

            if self.state == "LISTENING":
                primary   = QColor(16, 185, 129)
                secondary = QColor(52, 211, 153, 140)
                glow_scale = 1.0 + 0.22 * math.sin(self.phase * 2.8)
                ring_speed = 4.0
            elif self.state == "THINKING":
                primary   = QColor(245, 158, 11)
                secondary = QColor(251, 191, 36, 155)
                glow_scale = 1.0 + 0.14 * math.sin(self.phase * 3.2)
                ring_speed = 6.0
            elif self.state == "SPEAKING":
                primary   = QColor(168, 85, 247)
                secondary = QColor(192, 132, 252, 160)
                glow_scale = 1.0 + 0.28 * abs(math.sin(self.phase * 2.2))
                ring_speed = 3.0
            elif self.state == "NO_MIC":
                primary   = QColor(239, 68, 68)
                secondary = QColor(248, 113, 113, 110)
                glow_scale = 1.0 + 0.05 * math.sin(self.phase)
                ring_speed = 0.5
            elif self.state == "MUTED":
                primary   = QColor(100, 116, 139)
                secondary = QColor(148, 163, 184, 90)
                glow_scale = 1.0 + 0.03 * math.sin(self.phase * 0.5)
                ring_speed = 0.3
            else:  # IDLE
                primary   = QColor(56, 189, 248)
                secondary = QColor(14, 165, 233, 120)
                glow_scale = 1.0 + 0.09 * math.sin(self.phase)
                ring_speed = 1.2

            # Outer ambient glow
            halo_r = base_r * 1.9 * glow_scale
            grad = QRadialGradient(cx, cy, halo_r)
            grad.setColorAt(0.0, QColor(primary.red(), primary.green(), primary.blue(), 170))
            grad.setColorAt(0.55, QColor(secondary.red(), secondary.green(), secondary.blue(), 45))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(halo_r), int(halo_r))

            # Rotating outer HUD arcs
            angle_deg = int((self.phase * 18.0 * ring_speed) % 360)
            arc_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 185), 2.2)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.PenStyle.NoBrush)
            r_outer = 44
            painter.drawArc(int(cx - r_outer), int(cy - r_outer), r_outer * 2, r_outer * 2,
                            angle_deg * 16, 100 * 16)
            painter.drawArc(int(cx - r_outer), int(cy - r_outer), r_outer * 2, r_outer * 2,
                            (angle_deg + 180) * 16, 100 * 16)

            # Inner counter-rotating ring
            r_mid = 36
            mid_pen = QPen(QColor(secondary.red(), secondary.green(), secondary.blue(), 150), 1.5)
            mid_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(mid_pen)
            angle2 = int((-self.phase * 12.0 * ring_speed) % 360)
            painter.drawArc(int(cx - r_mid), int(cy - r_mid), r_mid * 2, r_mid * 2,
                            angle2 * 16, 70 * 16)

            # Core glowing circle
            core_r = base_r * glow_scale * 0.9
            core_grad = QRadialGradient(cx - 4, cy - 4, core_r)
            core_grad.setColorAt(0.0, QColor(255, 255, 255, 220))
            core_grad.setColorAt(0.35, QColor(primary.red(), primary.green(), primary.blue(), 230))
            core_grad.setColorAt(1.0, QColor(secondary.red(), secondary.green(), secondary.blue(), 110))
            painter.setBrush(QBrush(core_grad))
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1.0))
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(core_r), int(core_r))

            # Mute cross-out indicator
            if self.state == "MUTED":
                mute_pen = QPen(QColor(248, 113, 113, 200), 3.0)
                mute_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(mute_pen)
                offset = 10
                painter.drawLine(int(cx - offset), int(cy - offset), int(cx + offset), int(cy + offset))
                painter.drawLine(int(cx + offset), int(cy - offset), int(cx - offset), int(cy + offset))

            painter.end()
        except Exception as e:
            logger.debug("paintEvent error: %s", e)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class MiniWindow(QWidget):
    """
    Floating HUD window for VAX Voice Assistant.

    Signals:
      command_submitted(str)      – user sent text command
      ptt_clicked()               – push-to-talk triggered
      emergency_stop_clicked()    – stop all activity
      settings_requested()        – open settings dialog
      logs_requested()            – open log viewer
      turbo_toggled(bool)         – turbo mode on/off
      clear_memory_requested()    – wipe conversation memory
      mic_mute_toggled(bool)      – True = muted, False = unmuted
      volume_changed(int)         – 0-100 volume change
    """

    command_submitted       = Signal(str)
    ptt_clicked             = Signal()
    emergency_stop_clicked  = Signal()
    settings_requested      = Signal()
    logs_requested          = Signal()
    turbo_toggled           = Signal(bool)
    clear_memory_requested  = Signal()
    mic_mute_toggled        = Signal(bool)   # NEW
    volume_changed          = Signal(int)    # NEW

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self._mic_available   = False
        self._mic_label       = ""
        self._mic_muted       = bool(config_manager.get("voice", "mic_muted", False))
        self._drag_pos        = QPoint()

        # Window chrome
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(380, 540)
        self.resize(420, 620)

        self.setStyleSheet(DARK_THEME_QSS)
        self._build_ui()
        self._setup_shortcuts()
        self._position_bottom_right()
        if self._mic_muted:
            self.set_mic_muted(True, emit=False, log_msg=False)
        self._position_bottom_right()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Drop shadow
        self.container = QWidget(self)
        self.container.setObjectName("MainContainer")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(shadow)
        root_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        # ── 1. HEADER BAR ─────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(5)

        title = QLabel("🤖 VAX AI", self.container)
        title.setObjectName("HeaderTitle")

        self.status_badge = QLabel("READY", self.container)
        self.status_badge.setObjectName("StatusLabel")

        self.btn_mode = QPushButton("🛡️ NORMAL", self.container)
        self.btn_mode.setToolTip("Toggle Normal ↔ Turbo mode")
        self.btn_mode.clicked.connect(self._toggle_turbo_mode)
        self._sync_mode_button(bool(config_manager.get("general", "turbo_mode", False)))

        # --- NEW: Mic mute toggle button ---
        self.btn_mic_mute = QPushButton(self.container)
        self.btn_mic_mute.setObjectName("IconButton")
        self.btn_mic_mute.setFixedSize(28, 28)
        self.btn_mic_mute.setToolTip("Mute / Unmute Microphone")
        self.btn_mic_mute.clicked.connect(self._toggle_mic_mute)
        self._sync_mic_mute_button()

        btn_clear = QPushButton("🧹", self.container)
        btn_clear.setObjectName("IconButton")
        btn_clear.setFixedSize(28, 28)
        btn_clear.setToolTip("Clear Chat & Memory")
        btn_clear.clicked.connect(self._on_clear_chat)

        btn_logs = QPushButton("📋", self.container)
        btn_logs.setObjectName("IconButton")
        btn_logs.setFixedSize(28, 28)
        btn_logs.setToolTip("Action History & Audit Log")
        btn_logs.clicked.connect(self._safe_emit_logs)

        btn_settings = QPushButton("⚙️", self.container)
        btn_settings.setObjectName("IconButton")
        btn_settings.setFixedSize(28, 28)
        btn_settings.setToolTip("Settings")
        btn_settings.clicked.connect(self._safe_emit_settings)

        btn_minimize = QPushButton("—", self.container)
        btn_minimize.setObjectName("IconButton")
        btn_minimize.setFixedSize(28, 28)
        btn_minimize.setToolTip("Minimize to Tray")
        btn_minimize.clicked.connect(self.hide)

        header.addWidget(title)
        header.addWidget(self.status_badge)
        header.addWidget(self.btn_mode)
        header.addStretch()
        header.addWidget(self.btn_mic_mute)
        header.addWidget(btn_clear)
        header.addWidget(btn_logs)
        header.addWidget(btn_settings)
        header.addWidget(btn_minimize)
        layout.addLayout(header)

        # ── 2. MIC STATUS + VOLUME SLIDER ─────────────────────────────
        mic_vol_row = QHBoxLayout()
        mic_vol_row.setSpacing(6)

        self.mic_pill = QLabel("🎙️ Detecting microphone...", self.container)
        self.mic_pill.setStyleSheet("color: #64748b; font-size: 10px;")

        # --- NEW: Continuous Follow-up Conversation Toggle ---
        self.btn_followup = QPushButton(self.container)
        self.btn_followup.setFixedHeight(20)
        self.btn_followup.setToolTip(
            "Continuous Conversation Mode: listen automatically for follow-up questions after VAX replies"
        )
        self.btn_followup.clicked.connect(self._toggle_followup_mode)
        self._sync_followup_button(bool(config_manager.get("general", "continuous_conversation", True)))

        # Volume label left
        vol_lo = QLabel("🔈", self.container)
        vol_lo.setStyleSheet("color: #64748b; font-size: 11px;")
        vol_lo.setFixedWidth(16)

        # --- NEW: Volume slider ---
        self.vol_slider = QSlider(Qt.Orientation.Horizontal, self.container)
        self.vol_slider.setObjectName("VolumeSlider")
        self.vol_slider.setRange(0, 100)
        saved_vol = int(config_manager.get("voice", "volume", 80))
        self.vol_slider.setValue(saved_vol)
        self.vol_slider.setFixedWidth(74)
        self.vol_slider.setFixedHeight(16)
        self.vol_slider.setToolTip("Volume (0–100)")
        self.vol_slider.valueChanged.connect(self._on_volume_changed)

        vol_hi = QLabel("🔊", self.container)
        vol_hi.setStyleSheet("color: #64748b; font-size: 11px;")
        vol_hi.setFixedWidth(18)

        mic_vol_row.addWidget(self.mic_pill, stretch=1)
        mic_vol_row.addWidget(self.btn_followup)
        mic_vol_row.addWidget(vol_lo)
        mic_vol_row.addWidget(self.vol_slider)
        mic_vol_row.addWidget(vol_hi)
        layout.addLayout(mic_vol_row)

        # ── 3. ANIMATED ORB + STATUS ───────────────────────────────────
        orb_row = QHBoxLayout()
        orb_row.addStretch()
        self.orb = VoiceOrbWidget(self.container)
        orb_row.addWidget(self.orb)
        orb_row.addStretch()
        layout.addLayout(orb_row)

        self.status_text = QLabel(
            "Say 'Hey Jarvis', press Ctrl+Space, or click 🎙️",
            self.container,
        )
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.status_text.setWordWrap(True)
        layout.addWidget(self.status_text)

        # ── 4. QUICK ACTION CHIPS ──────────────────────────────────────
        chips_row = QHBoxLayout()
        chips_row.setSpacing(4)
        quick_actions = [
            ("🎵 Song",    "Bangla song play koro"),
            ("🌤️ Weather", "Ajker weather kemon?"),
            ("🖥️ PC",      "Amar PC-r CPU RAM o battery dekhao"),
            ("🌐 Chrome",  "Chrome open koro"),
        ]
        for label, cmd in quick_actions:
            chip = QPushButton(label, self.container)
            chip.setObjectName("QuickChip")
            chip.clicked.connect(lambda checked=False, c=cmd: self._submit_text(c))
            chips_row.addWidget(chip)

        # --- NEW: Memory facts chip ---
        btn_memory = QPushButton("🧠", self.container)
        btn_memory.setObjectName("QuickChip")
        btn_memory.setToolTip("Show saved memory facts")
        btn_memory.clicked.connect(self._show_memory_facts)
        chips_row.addWidget(btn_memory)

        layout.addLayout(chips_row)

        # ── 5. TRANSCRIPT ──────────────────────────────────────────────
        self.transcript = QTextEdit(self.container)
        self.transcript.setObjectName("TranscriptArea")
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "Ask anything in Bangla, Banglish, or English..."
        )
        layout.addWidget(self.transcript, stretch=1)

        # ── 6. INPUT DOCK ──────────────────────────────────────────────
        input_bar = QHBoxLayout()
        input_bar.setSpacing(5)

        self.input_field = QLineEdit(self.container)
        self.input_field.setObjectName("CommandInput")
        self.input_field.setPlaceholderText("Type command (Bangla / English)...")
        self.input_field.returnPressed.connect(self._on_send)

        self.btn_mic = QPushButton("🎙️", self.container)
        self.btn_mic.setObjectName("MicButton")
        self.btn_mic.setFixedSize(36, 36)
        self.btn_mic.setToolTip("Push-to-Talk (Ctrl+Space)")
        self.btn_mic.clicked.connect(self._safe_emit_ptt)

        btn_send = QPushButton("➤", self.container)
        btn_send.setObjectName("SendButton")
        btn_send.setFixedSize(36, 36)
        btn_send.setToolTip("Send Command")
        btn_send.clicked.connect(self._on_send)

        self.btn_stop = QPushButton("STOP", self.container)
        self.btn_stop.setObjectName("StopButton")
        self.btn_stop.setFixedSize(54, 36)
        self.btn_stop.setToolTip("Emergency Stop (Ctrl+Alt+Esc)")
        self.btn_stop.clicked.connect(self._safe_emit_emergency_stop)

        input_bar.addWidget(self.input_field, stretch=1)
        input_bar.addWidget(self.btn_mic)
        input_bar.addWidget(btn_send)
        input_bar.addWidget(self.btn_stop)
        layout.addLayout(input_bar)

        # Resize grip (bottom-right corner)
        grip_row = QHBoxLayout()
        grip_row.addStretch()
        self._size_grip = QSizeGrip(self.container)
        self._size_grip.setStyleSheet("background: transparent;")
        grip_row.addWidget(self._size_grip)
        layout.addLayout(grip_row)

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------
    def _setup_shortcuts(self):
        try:
            self._ptt_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
            self._ptt_shortcut.activated.connect(self._safe_emit_ptt)
        except Exception as e:
            logger.debug("Shortcut setup warning: %s", e)

    # ------------------------------------------------------------------
    # Mode / State Sync
    # ------------------------------------------------------------------
    def _sync_mode_button(self, is_turbo: bool):
        if is_turbo:
            self.btn_mode.setText("⚡ TURBO")
            self.btn_mode.setObjectName("ModePillTurbo")
        else:
            self.btn_mode.setText("🛡️ NORMAL")
            self.btn_mode.setObjectName("ModePillNormal")
        self.btn_mode.style().unpolish(self.btn_mode)
        self.btn_mode.style().polish(self.btn_mode)

    def _toggle_turbo_mode(self):
        current = bool(config_manager.get("general", "turbo_mode", False))
        new_val = not current
        config_manager.set("general", "turbo_mode", new_val)
        self._sync_mode_button(new_val)
        mode_name = "TURBO MODE ⚡" if new_val else "NORMAL MODE 🛡️"
        self.append_transcript("System", f"Switched to {mode_name}.", "#fbbf24" if new_val else "#34d399")
        try:
            self.turbo_toggled.emit(new_val)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Mic Mute Toggle (NEW)
    # ------------------------------------------------------------------
    def _sync_mic_mute_button(self):
        if self._mic_muted:
            self.btn_mic_mute.setText("🔇")
            self.btn_mic_mute.setToolTip("Microphone MUTED — click to unmute")
            self.btn_mic_mute.setStyleSheet(
                "QPushButton { color: #f87171; background: rgba(239,68,68,0.18); "
                "border: 1px solid #ef4444; border-radius: 6px; }"
                "QPushButton:hover { background: rgba(239,68,68,0.3); }"
            )
        else:
            self.btn_mic_mute.setText("🎙️")
            self.btn_mic_mute.setToolTip("Microphone ACTIVE — click to mute")
            self.btn_mic_mute.setStyleSheet(
                "QPushButton { color: #34d399; background: rgba(16,185,129,0.18); "
                "border: 1px solid #10b981; border-radius: 6px; }"
                "QPushButton:hover { background: rgba(16,185,129,0.3); }"
            )

    def sync_turbo_ui(self, is_turbo: bool):
        """Syncs turbo button look from external settings changes."""
        self._sync_mode_button(is_turbo)

    def _sync_followup_button(self, enabled: bool):
        if enabled:
            self.btn_followup.setText("💬 AUTO")
            self.btn_followup.setStyleSheet(
                "QPushButton { font-size: 9px; font-weight: 700; padding: 2px 7px; "
                "border-radius: 9px; color: #38bdf8; background: rgba(56,189,248,0.14); "
                "border: 1px solid rgba(56,189,248,0.40); }"
                "QPushButton:hover { background: rgba(56,189,248,0.28); }"
            )
        else:
            self.btn_followup.setText("💬 1-SHOT")
            self.btn_followup.setStyleSheet(
                "QPushButton { font-size: 9px; font-weight: 700; padding: 2px 7px; "
                "border-radius: 9px; color: #94a3b8; background: rgba(100,116,139,0.15); "
                "border: 1px solid rgba(100,116,139,0.35); }"
                "QPushButton:hover { background: rgba(100,116,139,0.28); }"
            )

    def _toggle_followup_mode(self):
        current = bool(config_manager.get("general", "continuous_conversation", True))
        new_val = not current
        config_manager.set("general", "continuous_conversation", new_val)
        self._sync_followup_button(new_val)
        msg = (
            "💬 Continuous Conversation ON — next question will listen automatically after reply."
            if new_val
            else "💬 Single-Turn Mode — say wake word or press Ctrl+Space for each question."
        )
        self.append_transcript("System", msg, "#38bdf8" if new_val else "#94a3b8")

    def _toggle_mic_mute(self):
        self.set_mic_muted(not self._mic_muted, emit=True, log_msg=True)

    def set_mic_muted(self, muted: bool, emit: bool = True, log_msg: bool = True):
        self._mic_muted = bool(muted)
        config_manager.set("voice", "mic_muted", self._mic_muted)
        self._sync_mic_mute_button()
        if self._mic_muted:
            self.orb.set_state("MUTED")
            self.status_badge.setText("MUTED")
            self.status_badge.setStyleSheet(
                "color: #94a3b8; background-color: rgba(100,116,139,0.18); "
                "border: 1px solid #64748b; font-weight: bold;"
            )
            self.status_text.setText("🔇 Microphone silenced — text-only mode")
            self.mic_pill.setText("🔇 Microphone Muted")
            self.mic_pill.setStyleSheet("color: #94a3b8; font-size: 10px;")
            if log_msg:
                self.append_transcript("System", "🔇 Microphone muted. Text-only mode active.", "#94a3b8")
        else:
            self.status_text.setText("🎙️ Microphone unmuted — resuming voice...")
            if log_msg:
                self.append_transcript("System", "🎙️ Microphone unmuted. Voice active.", "#34d399")
            self.set_state_idle()
        if emit:
            try:
                self.mic_mute_toggled.emit(self._mic_muted)
            except Exception:
                pass

    def is_mic_muted(self) -> bool:
        return self._mic_muted

    # ------------------------------------------------------------------
    # Volume Control (NEW)
    # ------------------------------------------------------------------
    def _on_volume_changed(self, value: int):
        try:
            config_manager.set("voice", "volume", value)
            self.volume_changed.emit(value)
        except Exception as e:
            logger.debug("Volume change error: %s", e)

    # ------------------------------------------------------------------
    # Memory Facts Viewer (NEW)
    # ------------------------------------------------------------------
    def _show_memory_facts(self):
        try:
            from vax.memory import memory_manager
            facts = memory_manager.get_all_facts()
            if not facts:
                self.append_transcript("Memory", "No saved facts yet. Tell me things to remember!", "#a78bfa")
                return
            lines = ["Saved Memory Facts:"]
            for key, val in facts.items():
                lines.append(f"• {key}: {val}")
            self.append_transcript("Memory", "\n".join(lines), "#a78bfa")
        except Exception as e:
            self.append_transcript("Memory", f"Could not load memory: {e}", "#f87171")

    # ------------------------------------------------------------------
    # Microphone Status (called from main.py)
    # ------------------------------------------------------------------
    def set_microphone_status(self, available: bool, detail: str = ""):
        self._mic_available = available
        self._mic_label = detail
        if available:
            short = (detail[:34] + "…") if len(detail) > 34 else detail
            self.mic_pill.setText(f"🎙️ Mic Active: {short}")
            self.mic_pill.setStyleSheet("color: #34d399; font-size: 10px;")
        else:
            self.mic_pill.setText(f"⚠️ {detail or 'No Microphone Detected'}")
            self.mic_pill.setStyleSheet("color: #f87171; font-size: 10px; font-weight: bold;")
            if not self._mic_muted:
                self.orb.set_state("NO_MIC")

    # ------------------------------------------------------------------
    # Chat / Clear
    # ------------------------------------------------------------------
    def _on_clear_chat(self):
        self.transcript.clear()
        try:
            self.clear_memory_requested.emit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Signal emitters (safe)
    # ------------------------------------------------------------------
    def _safe_emit_ptt(self):
        if self._mic_muted:
            self.append_transcript("System", "🔇 Mic muted — click 🎙️ in header to unmute.", "#94a3b8")
            return
        try:
            self.ptt_clicked.emit()
        except Exception as e:
            logger.error("Error triggering PTT: %s", e)

    def _safe_emit_logs(self):
        try:
            self.logs_requested.emit()
        except Exception as e:
            logger.error("Error opening logs: %s", e)

    def _safe_emit_settings(self):
        try:
            self.settings_requested.emit()
        except Exception as e:
            logger.error("Error opening settings: %s", e)

    def _safe_emit_emergency_stop(self):
        try:
            self.emergency_stop_clicked.emit()
        except Exception as e:
            logger.error("Error triggering emergency stop: %s", e)

    # ------------------------------------------------------------------
    # Window positioning
    # ------------------------------------------------------------------
    def _position_bottom_right(self):
        try:
            screen = QGuiApplication.primaryScreen().geometry()
            x = screen.width() - self.width() - 25
            y = screen.height() - self.height() - 60
            self.move(x, y)
        except Exception as e:
            logger.debug("Error positioning window: %s", e)

    # ------------------------------------------------------------------
    # Text submission
    # ------------------------------------------------------------------
    def _submit_text(self, text: str):
        clean = text.strip()
        if clean:
            self.append_transcript("You", clean, "#38bdf8")
            self.command_submitted.emit(clean)

    def _on_send(self):
        try:
            text = self.input_field.text().strip()
            if text:
                self.input_field.clear()
                self._submit_text(text)
        except Exception as e:
            logger.error("Error sending command: %s", e)

    # ------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------
    def append_transcript(self, sender: str, text: str, color: str = "#f1f5f9"):
        """Appends a styled message card to the transcript area."""
        try:
            clean_text = str(text) if text is not None else ""
            escaped_text = html.escape(clean_text).replace("\n", "<br>")
            is_error = sender.lower() in ("error", "warning") or clean_text.startswith("Error:")

            if is_error:
                entry_html = (
                    "<div style='background-color: rgba(239,68,68,0.14); "
                    "border-left: 3px solid #ef4444; padding:6px 8px; "
                    "margin-bottom:6px; border-radius:6px;'>"
                    f"<b style='color:#f87171;'>⚠️ {html.escape(sender)}:</b> "
                    f"<span style='color:#fecaca;'>{escaped_text}</span></div>"
                )
            elif sender.startswith("You"):
                entry_html = (
                    "<div style='background-color: rgba(56,189,248,0.10); "
                    "border-left: 3px solid #38bdf8; padding:6px 8px; "
                    "margin-bottom:6px; border-radius:6px;'>"
                    f"<b style='color:{color};'>{html.escape(sender)}:</b> {escaped_text}</div>"
                )
            elif sender == "VAX":
                entry_html = (
                    "<div style='background-color: rgba(16,185,129,0.10); "
                    "border-left: 3px solid #34d399; padding:6px 8px; "
                    "margin-bottom:6px; border-radius:6px;'>"
                    f"<b style='color:{color};'>🤖 VAX:</b> {escaped_text}</div>"
                )
            elif sender in ("Memory", "🧠 Memory"):
                entry_html = (
                    "<div style='background-color: rgba(167,139,250,0.10); "
                    "border-left: 3px solid #a78bfa; padding:6px 8px; "
                    "margin-bottom:6px; border-radius:6px;'>"
                    f"<b style='color:#a78bfa;'>🧠 Memory:</b><br>{escaped_text}</div>"
                )
            else:
                entry_html = (
                    f"<div style='margin-bottom:4px; font-size:12px;'>"
                    f"<b style='color:{color};'>{html.escape(sender)}:</b> {escaped_text}</div>"
                )

            self.transcript.append(entry_html)
            cursor = self.transcript.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.transcript.setTextCursor(cursor)
        except Exception as e:
            logger.error("Failed to append transcript: %s", e)
            try:
                self.transcript.insertPlainText(f"\n{sender}: {text}\n")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # State management (called from main.py via signal bridge)
    # ------------------------------------------------------------------
    def set_state_listening(self, is_followup: bool = False):
        if self._mic_muted:
            return
        try:
            self.orb.set_state("LISTENING")
            self.status_badge.setText("FOLLOW-UP" if is_followup else "LISTENING")
            self.status_badge.setStyleSheet(
                "color: #34d399; background-color: rgba(16,185,129,0.18); "
                "border: 1px solid #10b981; font-weight: bold;"
            )
            if is_followup:
                self.status_text.setText("💬 Follow-up listening… speak next question (no wake word needed)")
            else:
                self.status_text.setText("Listening… speak in Bangla or English")
        except Exception as e:
            logger.debug("Error setting listening state: %s", e)

    def set_state_thinking(self, message: str = "Thinking..."):
        try:
            self.orb.set_state("THINKING")
            self.status_badge.setText("THINKING")
            self.status_badge.setStyleSheet(
                "color: #fbbf24; background-color: rgba(245,158,11,0.18); "
                "border: 1px solid #f59e0b; font-weight: bold;"
            )
            self.status_text.setText(message)
        except Exception as e:
            logger.debug("Error setting thinking state: %s", e)

    def set_state_speaking(self):
        try:
            self.orb.set_state("SPEAKING")
            self.status_badge.setText("SPEAKING")
            self.status_badge.setStyleSheet(
                "color: #c084fc; background-color: rgba(168,85,247,0.18); "
                "border: 1px solid #a855f7; font-weight: bold;"
            )
            self.status_text.setText("Speaking reply...")
        except Exception as e:
            logger.debug("Error setting speaking state: %s", e)

    def set_state_idle(self):
        try:
            if self._mic_muted:
                # Stay in MUTED state
                return
            if not self._mic_available:
                self.orb.set_state("NO_MIC")
                self.status_badge.setText("TEXT ONLY")
                self.status_badge.setStyleSheet(
                    "color: #f87171; background-color: rgba(239,68,68,0.15); "
                    "border: 1px solid #ef4444; font-weight: bold;"
                )
                self.status_text.setText("No microphone — type below or connect mic & click 🎙️")
            else:
                self.orb.set_state("IDLE")
                self.status_badge.setText("READY")
                self.status_badge.setStyleSheet(
                    "color: #38bdf8; background-color: rgba(56,189,248,0.14); "
                    "border: 1px solid rgba(56,189,248,0.35); font-weight: bold;"
                )
                wake = config_manager.get("general", "wake_word", "hey jarvis")
                self.status_text.setText(f"Say '{wake}', press Ctrl+Space, or click 🎙️")
        except Exception as e:
            logger.debug("Error setting idle state: %s", e)

    # ------------------------------------------------------------------
    # Draggable window
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        try:
            if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
