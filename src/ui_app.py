import sys
import threading
import time
from datetime import datetime
import os
import re
from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QMenu,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.automation import organize_downloads
from modules.command_handler import (
    clear_file_selection_handler,
    handle_command,
    handle_command_stream,
    set_file_selection_handler,
)
from utils.safety import clear_confirm_handler, set_confirm_handler
from utils.suggestions import get_action_suggestions
from utils.voice import listen, preview_tts, reset_tts_backend, speak, VOICE_CHARACTERS
from utils.memory import (
    export_memory_history,
    get_memory_insights,
    get_user_preferences,
    reset_user_profile_learning,
    set_user_preferences,
)
from utils.personas import get_persona_meta, get_persona_options, normalize_persona_id


SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_ROOT)
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


class CommandWorker(QThread):
    partial = pyqtSignal(str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, command_text):
        super().__init__()
        self.command_text = command_text

    def run(self):
        try:
            response_buffer = ""
            for chunk in handle_command_stream(self.command_text):
                text = str(chunk)
                if not text:
                    continue
                response_buffer += text
                self.partial.emit(response_buffer)
            self.finished.emit(str(response_buffer))
        except Exception as exc:
            self.failed.emit(f"Error: {exc}")


class ActionWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, action_type):
        super().__init__()
        self.action_type = action_type

    def run(self):
        try:
            if self.action_type == "organize_downloads":
                result = organize_downloads()
            elif self.action_type == "repeat_warning":
                result = "Try creating a custom command for this task."
            else:
                result = "No action mapped for this suggestion."
            self.finished.emit(str(result))
        except Exception as exc:
            self.failed.emit(f"Error: {exc}")


class VoicePreviewWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, text, character):
        super().__init__()
        self.text = text
        self.character = character

    def run(self):
        try:
            preview_tts(
                text=self.text,
                character=self.character,
            )
            self.finished.emit("Voice test completed.")
        except Exception as exc:
            self.failed.emit(f"Voice test failed: {exc}")


class BackgroundVoiceWorker(QThread):
    status = pyqtSignal(str)
    activated = pyqtSignal()
    deactivated = pyqtSignal(str)
    command_heard = pyqtSignal(str)
    response_ready = pyqtSignal(str)

    def __init__(self, inactivity_seconds=60, voice_copy=None):
        super().__init__()
        self.inactivity_seconds = max(10, int(inactivity_seconds))
        self._running = True
        self._voice_copy = dict(voice_copy or {})
        self._wake_variants = ("hey winter", "hi winter", "a winter", "winter")
        self._sleep_phrases = {
            "sleep",
            "go to sleep",
            "stop listening",
            "stop listen",
            "sleep mode",
            "so ja",
            "pause",
        }

    def stop(self):
        self._running = False

    def set_voice_copy(self, voice_copy):
        self._voice_copy = dict(voice_copy or {})

    def _line(self, key, fallback):
        return str(self._voice_copy.get(key, fallback))

    def _is_noise(self, text):
        lowered = str(text).strip().lower()
        return lowered in {"", "could not understand"} or lowered.startswith("error:")

    def _is_wake(self, text):
        lowered = str(text).strip().lower()
        return any(variant in lowered for variant in self._wake_variants)

    def _is_sleep(self, text):
        lowered = str(text).strip().lower()
        return any(phrase in lowered for phrase in self._sleep_phrases)

    def run(self):
        active = False
        last_command_at = 0.0
        self.status.emit(self._line("status_start", "Background mode on. Say 'Hey Winter' to activate."))
        speak(self._line("speak_start", "Background mode enabled. Say Hey Winter to activate me."))

        while self._running:
            if active and (time.time() - last_command_at) >= self.inactivity_seconds:
                active = False
                msg = self._line(
                    "inactive_notice",
                    "No command for 1 minute. Winter inactive now. Say Hey Winter to activate again.",
                )
                self.deactivated.emit(msg)
                speak(msg)

            heard = listen(timeout=4, phrase_time_limit=8)
            if self._is_noise(heard):
                continue

            if not active:
                if self._is_wake(heard):
                    active = True
                    last_command_at = time.time()
                    self.activated.emit()
                    speak(self._line("wake_spoken", "Winter activated. I am ready for your commands."))
                continue

            if self._is_sleep(heard):
                active = False
                msg = self._line("sleep_notice", "Winter sleeping. Say Hey Winter to activate again.")
                self.deactivated.emit(msg)
                speak(msg)
                continue

            if self._is_wake(heard):
                speak(self._line("already_active", "I am active and listening."))
                continue

            self.command_heard.emit(str(heard))
            try:
                response = handle_command(heard)
            except Exception as exc:
                response = f"Error: {exc}"

            self.response_ready.emit(str(response))
            speak(str(response))
            last_command_at = time.time()
            self.status.emit("Winter active. Listening for next command.")


class ChatBubble(QFrame):
    def __init__(self, role, message):
        super().__init__()
        self.setObjectName("bubble")
        self.setMaximumHeight(0)
        self.setMaximumWidth(720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        role_text = "You" if role == "user" else "Winter"
        role_label = QLabel(role_text)
        role_label.setStyleSheet(
            "color: #8ad8dc; font-size: 10px; font-weight: 600; letter-spacing: 1px;"
        )

        self.message_label = QLabel(str(message))
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.message_label.setStyleSheet("color: #dfe2eb; font-size: 14px;")

        layout.addWidget(role_label)
        layout.addWidget(self.message_label)

        if role == "user":
            self.setStyleSheet(
                """
                #bubble {
                    background-color: #12383b;
                    border: 1px solid rgba(0, 245, 255, 0.22);
                    border-radius: 12px;
                }
                """
            )
            self.message_label.setStyleSheet("color: #c6f7fa; font-size: 14px; font-weight: 500;")
        else:
            self.setStyleSheet(
                """
                #bubble {
                    background-color: #111111;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }
                """
            )
            self.message_label.setStyleSheet("color: #dfe2eb; font-size: 14px;")

        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.opacity.setOpacity(0.0)

        self.opacity_anim = QPropertyAnimation(self.opacity, b"opacity", self)
        self.opacity_anim.setDuration(120)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.height_anim = QPropertyAnimation(self, b"maximumHeight", self)
        self.height_anim.setDuration(140)
        self.height_anim.setEasingCurve(QEasingCurve.OutCubic)

        QTimer.singleShot(0, self.play_animation)

    def play_animation(self):
        target = self.sizeHint().height() + 8
        self.height_anim.setStartValue(0)
        self.height_anim.setEndValue(target)
        self.height_anim.start()
        self.opacity_anim.start()

    def set_message(self, message):
        self.message_label.setText(str(message))
        target = self.sizeHint().height() + 8
        self.setMaximumHeight(target)
        self.updateGeometry()


class AIAssistantUI(QWidget):
    append_bubble_signal = pyqtSignal(str, str)
    ui_task_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Winter AI")
        self.resize(1080, 720)

        self.command_worker = None
        self.action_worker = None
        self.voice_preview_worker = None
        self.background_voice_worker = None
        self.streaming_ai_row = None
        self.streaming_ai_bubble = None
        self.streaming_ai_text = ""
        self.streaming_tts_index = 0

        self.backend_active = True
        self.typing_timer = QTimer(self)
        self.typing_step = 0
        self.tray_icon = None
        self.tray_menu = None
        self.tray_status_action = None
        self.active_persona_id = normalize_persona_id(get_user_preferences().get("assistant_persona", "balanced"))

        self._build_ui()
        self._apply_persona_visuals(self.active_persona_id)
        self._play_window_intro()
        self._setup_tray()
        self.append_bubble_signal.connect(self._append_bubble_ui, Qt.QueuedConnection)
        self.ui_task_signal.connect(self._execute_ui_callable, Qt.QueuedConnection)
        self._append_bubble("ai", self._persona_text("welcome", "Hi boss, kaise ho? Kuch help chahiye?"))

        set_confirm_handler(self._confirm_action)
        set_file_selection_handler(self._select_file_option)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Winter AI: Ready")

        self.tray_menu = QMenu(self)

        self.tray_status_action = QAction("Status: Ready", self)
        self.tray_status_action.setEnabled(False)

        restore_action = QAction("Restore Window", self)
        restore_action.triggered.connect(self._restore_from_tray)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_from_tray)

        self.tray_menu.addAction(self.tray_status_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(restore_action)
        self.tray_menu.addAction(quit_action)

        if self.tray_icon is not None:
            self.tray_icon.setContextMenu(self.tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
            self._update_tray_status("Ready")

    def _update_tray_status(self, status_text):
        text = str(status_text)
        if self.tray_icon is None:
            return

        self.tray_icon.setToolTip(f"Winter AI: {text}")
        if self.tray_status_action is not None:
            self.tray_status_action.setText(f"Status: {text}")

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self.close()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()

    def _build_ui(self):
        self.setObjectName("appRoot")
        self._base_stylesheet = """
            QWidget#appRoot {
                background-color: #000000;
                color: #dfe2eb;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }
            QWidget {
                color: #dfe2eb;
            }
            QFrame#sidebar {
                background-color: #030303;
                border-radius: 0px;
            }
            QFrame#mainArea {
                background-color: #050505;
            }
            QFrame#statsPanel {
                background-color: #020202;
            }
            QLabel#appTitle {
                color: #00f5ff;
                font-size: 24px;
                font-weight: 700;
                font-family: 'Space Grotesk', 'Inter', sans-serif;
            }
            QLabel#sidebarMeta {
                color: #6f8399;
                font-size: 11px;
            }
            QPushButton {
                background-color: #141414;
                border: none;
                border-radius: 10px;
                padding: 10px 14px;
                color: #dfe2eb;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1f1f1f;
            }
            QPushButton#primary {
                background-color: #00f5ff;
                color: #003739;
            }
            QPushButton#primary:hover {
                background-color: #63f7ff;
            }
            QPushButton#navActive {
                background-color: rgba(0, 245, 255, 0.14);
                color: #00f5ff;
                text-align: left;
                border-left: 2px solid #00f5ff;
                border-radius: 0px;
                padding-left: 14px;
            }
            QPushButton#navPassive {
                background-color: transparent;
                color: #95a5b8;
                text-align: left;
                border-radius: 0px;
                padding-left: 16px;
            }
            QPushButton#navPassive:hover {
                background-color: rgba(255, 255, 255, 0.06);
                color: #dfe2eb;
            }
            QLabel#statusChip {
                background: rgba(0, 245, 255, 0.10);
                color: #95d1d4;
                border-radius: 9px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#typingHint {
                color: #8a98ab;
                font-size: 11px;
                letter-spacing: 1px;
            }
            QFrame#chatCanvas {
                background-color: #0b0b0d;
                border-radius: 14px;
                border: 1px solid rgba(0, 245, 255, 0.10);
            }
            QLineEdit {
                background: transparent;
                border: none;
                padding: 10px 12px;
                color: #dfe2eb;
                font-size: 14px;
            }
            QLineEdit:focus {
                background: transparent;
            }
            QFrame#inputDock {
                background-color: rgba(20, 20, 20, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QGroupBox {
                border: none;
                border-radius: 16px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: 600;
                color: #e9feff;
                background-color: #101010;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                color: #00f5ff;
            }
            QComboBox, QTextEdit {
                background-color: #171717;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 8px 10px;
                min-height: 18px;
                color: #dfe2eb;
            }
            QComboBox::drop-down {
                border: none;
                width: 26px;
            }
            QLineEdit {
                background-color: #171717;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px 12px;
                color: #dfe2eb;
                font-size: 14px;
                min-height: 18px;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid rgba(0, 245, 255, 0.35);
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QAbstractScrollArea, QAbstractScrollArea QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                width: 7px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(132, 148, 149, 0.50);
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background: #242424;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: ACCENT_COLOR;
            }
            """
        self.setStyleSheet(self._base_stylesheet.replace("ACCENT_COLOR", "#00f5ff"))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 20)
        sidebar_layout.setSpacing(10)

        control_title = QLabel("CONTROL UNIT")
        control_title.setObjectName("appTitle")
        control_title.setStyleSheet("font-size: 24px;")
        control_meta = QLabel("v1.0.4-stable")
        control_meta.setObjectName("sidebarMeta")

        self.chat_nav_btn = QPushButton("Chat")
        self.chat_nav_btn.setObjectName("navActive")
        self.chat_nav_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(0))

        self.settings_nav_btn = QPushButton("Settings")
        self.settings_nav_btn.setObjectName("navPassive")
        self.settings_nav_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))

        self.upgrade_btn = QPushButton("UPGRADE PLAN")
        self.upgrade_btn.setStyleSheet(
            "QPushButton { background-color: #242424; color: #95d1d4; letter-spacing: 1px; font-size: 11px; }"
            "QPushButton:hover { background-color: #2e2e2e; }"
        )

        sidebar_layout.addWidget(control_title)
        sidebar_layout.addWidget(control_meta)
        sidebar_layout.addSpacing(24)
        sidebar_layout.addWidget(self.chat_nav_btn)
        sidebar_layout.addWidget(self.settings_nav_btn)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(self.upgrade_btn)

        main_area = QFrame()
        main_area.setObjectName("mainArea")
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(18, 14, 18, 12)
        main_layout.setSpacing(10)

        header = QHBoxLayout()
        header_title = QLabel("WINTER AI")
        header_title.setStyleSheet(
            "color: #00f5ff; font-size: 17px; font-weight: 700; letter-spacing: 1px; font-family: 'Space Grotesk';"
        )

        self.status_chip = QLabel("Backend Active")
        self.status_chip.setObjectName("statusChip")

        self.backend_toggle_btn = QPushButton("Pause")
        self.backend_toggle_btn.clicked.connect(self.toggle_backend)
        self.backend_toggle_btn.setFixedWidth(92)

        header.addWidget(header_title)
        header.addStretch()
        header.addWidget(self.status_chip)
        header.addWidget(self.backend_toggle_btn)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; background: #050505; }")

        chat_tab = QWidget()
        chat_tab_layout = QVBoxLayout(chat_tab)
        chat_tab_layout.setContentsMargins(0, 0, 0, 0)
        chat_tab_layout.setSpacing(0)

        self.typing_label = QLabel("")
        self.typing_label.setObjectName("typingHint")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.viewport().setStyleSheet("background-color: transparent;")

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(22, 12, 22, 12)
        self.chat_layout.setSpacing(14)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_container)

        chat_canvas = QFrame()
        chat_canvas.setObjectName("chatCanvas")
        chat_canvas_layout = QVBoxLayout(chat_canvas)
        chat_canvas_layout.setContentsMargins(0, 0, 0, 0)
        chat_canvas_layout.addWidget(self.scroll)

        input_dock = QFrame()
        input_dock.setObjectName("inputDock")
        input_dock_layout = QHBoxLayout(input_dock)
        input_dock_layout.setContentsMargins(8, 8, 8, 8)
        input_dock_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message Winter AI...")
        self.input_field.returnPressed.connect(self.process_input)

        self.background_btn = QPushButton("Background")
        self.background_btn.setFixedWidth(110)
        self.background_btn.clicked.connect(self.enable_background_mode)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self.process_input)
        self.send_btn.setFixedWidth(78)

        input_dock_layout.addWidget(self.input_field)
        input_dock_layout.addWidget(self.background_btn)
        input_dock_layout.addWidget(self.send_btn)

        chat_tab_layout.setContentsMargins(8, 8, 8, 8)
        chat_tab_layout.setSpacing(10)
        chat_tab_layout.addWidget(self.typing_label)
        chat_tab_layout.addWidget(chat_canvas, 1)
        chat_tab_layout.addWidget(input_dock)

        settings_tab = QWidget()
        settings_tab_layout = QVBoxLayout(settings_tab)
        settings_tab_layout.setContentsMargins(8, 8, 8, 8)
        settings_tab_layout.setSpacing(0)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.viewport().setStyleSheet("background-color: transparent;")

        settings_container = QWidget()
        settings_container.setStyleSheet("background: transparent;")
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(10, 6, 10, 20)
        settings_layout.setSpacing(18)

        self.settings_scroll.setWidget(settings_container)
        settings_tab_layout.addWidget(self.settings_scroll)

        persona_group = QGroupBox("Persona")
        persona_layout = QGridLayout(persona_group)
        persona_layout.setContentsMargins(14, 18, 14, 14)
        persona_layout.setHorizontalSpacing(16)
        persona_layout.setVerticalSpacing(12)
        persona_layout.setColumnStretch(0, 1)
        persona_layout.setColumnStretch(1, 2)

        persona_info = QLabel("Tune language, tone, and response style for adaptive behavior.")
        persona_info.setStyleSheet("color: #9aa9bb; font-size: 12px;")
        persona_info.setWordWrap(True)

        current_prefs = get_user_preferences()

        self.persona_preset_combo = QComboBox()
        self.persona_preset_combo.addItems(get_persona_options())
        self.persona_preset_combo.setCurrentText(
            normalize_persona_id(current_prefs.get("assistant_persona", "balanced"))
        )
        self.persona_preset_combo.currentTextChanged.connect(self._update_persona_description)

        self.persona_description = QLabel("")
        self.persona_description.setStyleSheet("color: #9aa9bb; font-size: 12px;")
        self.persona_description.setWordWrap(True)

        self.save_persona_btn = QPushButton("Save Persona")
        self.save_persona_btn.clicked.connect(self.save_persona_preset)

        self.persona_btn = QPushButton("Open Persona Settings")
        self.persona_btn.clicked.connect(self.open_persona_settings)
        self.reset_btn = QPushButton("Reset Persona Learning")
        self.reset_btn.clicked.connect(self.reset_persona_from_ui)

        persona_layout.addWidget(persona_info, 0, 0, 1, 2)
        persona_layout.addWidget(QLabel("AI Persona"), 1, 0)
        persona_layout.addWidget(self.persona_preset_combo, 1, 1)
        persona_layout.addWidget(self.persona_description, 2, 0, 1, 2)
        persona_layout.addWidget(self.save_persona_btn, 3, 0)
        persona_layout.addWidget(self.persona_btn, 3, 1)
        persona_layout.addWidget(self.reset_btn, 4, 0, 1, 2)
        self._update_persona_description(self.persona_preset_combo.currentText())

        memory_group = QGroupBox("Memory")
        memory_layout = QGridLayout(memory_group)
        memory_layout.setContentsMargins(14, 18, 14, 14)
        memory_layout.setHorizontalSpacing(16)
        memory_layout.setVerticalSpacing(12)
        memory_layout.setColumnStretch(0, 1)
        memory_layout.setColumnStretch(1, 1)

        memory_info = QLabel("View memory insights and export full memory when needed.")
        memory_info.setStyleSheet("color: #9aa9bb; font-size: 12px;")
        memory_info.setWordWrap(True)

        self.insights_btn = QPushButton("Open Insights")
        self.insights_btn.clicked.connect(self.show_memory_insights)
        self.export_btn = QPushButton("Export Memory")
        self.export_btn.clicked.connect(self.export_memory_from_ui)

        memory_layout.addWidget(memory_info, 0, 0, 1, 2)
        memory_layout.addWidget(self.insights_btn, 1, 0)
        memory_layout.addWidget(self.export_btn, 1, 1)

        live_group = QGroupBox("Live Web")
        live_layout = QGridLayout(live_group)
        live_layout.setContentsMargins(14, 18, 14, 14)
        live_layout.setHorizontalSpacing(16)
        live_layout.setVerticalSpacing(12)
        live_layout.setColumnStretch(0, 1)
        live_layout.setColumnStretch(1, 2)

        live_info = QLabel("Control internet access and preferred news feed locale for latest updates.")
        live_info.setStyleSheet("color: #9aa9bb; font-size: 12px;")
        live_info.setWordWrap(True)

        self.live_web_toggle = QCheckBox("Enable Live Web Access")
        self.live_web_toggle.setChecked(bool(current_prefs.get("live_web_access", True)))
        self.live_web_toggle.setStyleSheet("color: #cfe5f2; font-size: 12px;")

        self.news_region_combo = QComboBox()
        self.news_region_combo.addItems(["in", "us", "gb", "au", "ca"])
        self.news_region_combo.setCurrentText(str(current_prefs.get("preferred_news_region", "in")).lower())

        self.news_language_combo = QComboBox()
        self.news_language_combo.addItems(["en", "hi"])
        self.news_language_combo.setCurrentText(str(current_prefs.get("preferred_news_language", "en")).lower())

        self.web_mode_combo = QComboBox()
        self.web_mode_combo.addItems(["off", "smart", "always"])
        self.web_mode_combo.setCurrentText(str(current_prefs.get("web_search_mode", "smart")).lower())

        self.save_live_web_btn = QPushButton("Save Live Web Settings")
        self.save_live_web_btn.clicked.connect(self.save_live_web_settings)

        live_layout.addWidget(live_info, 0, 0, 1, 2)
        live_layout.addWidget(self.live_web_toggle, 1, 0, 1, 2)
        live_layout.addWidget(QLabel("News Region"), 2, 0)
        live_layout.addWidget(self.news_region_combo, 2, 1)
        live_layout.addWidget(QLabel("News Language"), 3, 0)
        live_layout.addWidget(self.news_language_combo, 3, 1)
        live_layout.addWidget(QLabel("Web Search Mode"), 4, 0)
        live_layout.addWidget(self.web_mode_combo, 4, 1)
        live_layout.addWidget(self.save_live_web_btn, 5, 0, 1, 2)

        tts_group = QGroupBox("Voice")
        tts_layout = QGridLayout(tts_group)
        tts_layout.setContentsMargins(14, 18, 14, 14)
        tts_layout.setHorizontalSpacing(16)
        tts_layout.setVerticalSpacing(12)
        tts_layout.setColumnStretch(0, 1)
        tts_layout.setColumnStretch(1, 2)

        tts_info = QLabel(
            "Choose your assistant's Voice Identity.\n"
            "Cloud voices need internet. Local Neural models download once on first use (~50MB).\n"
            "Kokoro local voices run fully offline after first download and are fastest on GPU.\n"
            "If CUDA is available, Kokoro uses GPU automatically for lower latency."
        )
        tts_info.setStyleSheet("color: #9aa9bb; font-size: 12px;")
        tts_info.setWordWrap(True)

        self.tts_character_combo = QComboBox()
        self.tts_character_combo.addItems(list(VOICE_CHARACTERS.keys()))
        self.tts_character_combo.setCurrentText(self._read_env_value("TTS_CHARACTER", "Ryan (Kokoro Local, Male)"))
        self.tts_character_combo.currentTextChanged.connect(self.save_tts_settings)

        self.test_voice_btn = QPushButton("Test Identity")
        self.test_voice_btn.clicked.connect(self.test_tts_voice)
        self.test_voice_btn.setMinimumHeight(42)

        for widget in (
            self.persona_preset_combo,
            self.news_region_combo,
            self.news_language_combo,
            self.web_mode_combo,
            self.tts_character_combo,
        ):
            widget.setMinimumHeight(40)

        tts_layout.addWidget(tts_info, 0, 0, 1, 2)
        tts_layout.addWidget(QLabel("Voice Identity"), 1, 0)
        tts_layout.addWidget(self.tts_character_combo, 1, 1)
        tts_layout.addWidget(self.test_voice_btn, 2, 0, 1, 2)

        settings_layout.addWidget(persona_group)
        settings_layout.addWidget(memory_group)
        settings_layout.addWidget(live_group)
        settings_layout.addWidget(tts_group)
        settings_layout.addStretch()

        self.tabs.addTab(chat_tab, "Chat")
        self.tabs.addTab(settings_tab, "Settings")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addLayout(header)
        main_layout.addWidget(self.tabs)

        stats_panel = QFrame()
        stats_panel.setObjectName("statsPanel")
        stats_panel.setFixedWidth(260)
        stats_layout = QVBoxLayout(stats_panel)
        stats_layout.setContentsMargins(16, 20, 16, 20)
        stats_layout.setSpacing(14)

        stats_title = QLabel("ENVIRONMENT STATS")
        stats_title.setStyleSheet(
            "color: #00f5ff; font-size: 11px; font-weight: 700; letter-spacing: 2px; font-family: 'Space Grotesk';"
        )

        cpu_row = QHBoxLayout()
        cpu_label = QLabel("CPU Usage")
        cpu_label.setStyleSheet("color: #98a7ba; font-size: 12px;")
        cpu_value = QLabel("14%")
        cpu_value.setStyleSheet("color: #9ecfe4; font-size: 12px;")
        cpu_row.addWidget(cpu_label)
        cpu_row.addStretch()
        cpu_row.addWidget(cpu_value)
        cpu_bar = QProgressBar()
        cpu_bar.setRange(0, 100)
        cpu_bar.setValue(14)
        cpu_bar.setTextVisible(False)

        mem_row = QHBoxLayout()
        mem_label = QLabel("Memory")
        mem_label.setStyleSheet("color: #98a7ba; font-size: 12px;")
        mem_value = QLabel("2.4 / 16 GB")
        mem_value.setStyleSheet("color: #9ecfe4; font-size: 12px;")
        mem_row.addWidget(mem_label)
        mem_row.addStretch()
        mem_row.addWidget(mem_value)
        mem_bar = QProgressBar()
        mem_bar.setRange(0, 100)
        mem_bar.setValue(18)
        mem_bar.setTextVisible(False)

        model_title = QLabel("MODEL PARAMETERS")
        model_title.setStyleSheet(
            "color: #6f8399; font-size: 10px; letter-spacing: 2px; font-weight: 600; font-family: 'Space Grotesk';"
        )

        temp_row = QHBoxLayout()
        temp_label = QLabel("Temperature")
        temp_value = QLabel("0.7")
        top_p_row = QHBoxLayout()
        top_p_label = QLabel("Top P")
        top_p_value = QLabel("0.9")
        max_token_row = QHBoxLayout()
        max_token_label = QLabel("Max Tokens")
        max_token_value = QLabel("2048")
        for key_label, value_label, row in (
            (temp_label, temp_value, temp_row),
            (top_p_label, top_p_value, top_p_row),
            (max_token_label, max_token_value, max_token_row),
        ):
            key_label.setStyleSheet("color: #c2cfdf; font-size: 12px;")
            value_label.setStyleSheet("color: #c2cfdf; font-size: 12px;")
            row.addWidget(key_label)
            row.addStretch()
            row.addWidget(value_label)

        stats_layout.addWidget(stats_title)
        stats_layout.addSpacing(8)
        stats_layout.addLayout(cpu_row)
        stats_layout.addWidget(cpu_bar)
        stats_layout.addLayout(mem_row)
        stats_layout.addWidget(mem_bar)
        stats_layout.addSpacing(20)
        stats_layout.addWidget(model_title)
        stats_layout.addLayout(temp_row)
        stats_layout.addLayout(top_p_row)
        stats_layout.addLayout(max_token_row)
        stats_layout.addStretch()

        root.addWidget(sidebar)
        root.addWidget(main_area, 1)
        root.addWidget(stats_panel)
        self.header_title = header_title
        self.control_title = control_title
        self.stats_title = stats_title
        self.model_title = model_title

    def _play_window_intro(self):
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.window_opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        self.window_opacity_anim.setDuration(220)
        self.window_opacity_anim.setStartValue(0.0)
        self.window_opacity_anim.setEndValue(1.0)
        self.window_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.window_opacity_anim.start()

    def _current_persona(self):
        return get_persona_meta(self.active_persona_id)

    def _persona_text(self, key, fallback):
        return str(self._current_persona().get(key, fallback))

    def _persona_voice_copy(self):
        return {
            "status_start": self._persona_text("voice_status_start", "Background mode on. Say 'Hey Winter' to activate."),
            "speak_start": self._persona_text("voice_speak_start", "Background mode enabled. Say Hey Winter to activate me."),
            "inactive_notice": self._persona_text(
                "voice_inactive_notice",
                "No command for 1 minute. Winter inactive now. Say Hey Winter to activate again.",
            ),
            "wake_spoken": self._persona_text("voice_wake_spoken", "Winter activated. I am ready for your commands."),
            "sleep_notice": self._persona_text("voice_sleep_notice", "Winter sleeping. Say Hey Winter to activate again."),
            "already_active": self._persona_text("voice_already_active", "I am active and listening."),
        }

    def _apply_persona_visuals(self, persona_id):
        self.active_persona_id = normalize_persona_id(persona_id)
        persona = get_persona_meta(self.active_persona_id)
        accent = str(persona.get("accent", "#00f5ff"))
        self.setStyleSheet(self._base_stylesheet.replace("ACCENT_COLOR", accent))

        if hasattr(self, "control_title"):
            self.control_title.setStyleSheet(
                f"font-size: 24px; color: {accent};"
            )
        if hasattr(self, "header_title"):
            self.header_title.setStyleSheet(
                f"color: {accent}; font-size: 17px; font-weight: 700; letter-spacing: 1px; font-family: 'Space Grotesk';"
            )
        if hasattr(self, "stats_title"):
            self.stats_title.setStyleSheet(
                f"color: {accent}; font-size: 11px; font-weight: 700; letter-spacing: 2px; font-family: 'Space Grotesk';"
            )
        if hasattr(self, "model_title"):
            self.model_title.setStyleSheet(
                f"color: {accent}; font-size: 10px; letter-spacing: 2px; font-weight: 600; font-family: 'Space Grotesk';"
            )

        self._update_persona_description(self.active_persona_id)
        if self.background_voice_worker is not None and self.background_voice_worker.isRunning():
            self.background_voice_worker.set_voice_copy(self._persona_voice_copy())
        if getattr(self, "backend_active", True):
            self._set_status_active(self._persona_text("status_active", "Backend Active"))
        else:
            self._set_status_waiting(self._persona_text("status_waiting", "Backend Paused"))

    def _on_tab_changed(self, index):
        if index == 0:
            self.chat_nav_btn.setObjectName("navActive")
            self.settings_nav_btn.setObjectName("navPassive")
        else:
            self.chat_nav_btn.setObjectName("navPassive")
            self.settings_nav_btn.setObjectName("navActive")

        self.chat_nav_btn.style().unpolish(self.chat_nav_btn)
        self.chat_nav_btn.style().polish(self.chat_nav_btn)
        self.settings_nav_btn.style().unpolish(self.settings_nav_btn)
        self.settings_nav_btn.style().polish(self.settings_nav_btn)

    def _append_bubble(self, role, message):
        if QThread.currentThread() != self.thread():
            self.append_bubble_signal.emit(str(role), str(message))
            return
        self._append_bubble_ui(role, message)

    def _append_bubble_ui(self, role, message):
        bubble = ChatBubble(role, message)
        row = self._build_bubble_row(role, bubble)
        index = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(index, row)
        self.chat_container.adjustSize()
        self.chat_container.updateGeometry()
        self.scroll.viewport().update()
        self.update()
        bubble.height_anim.valueChanged.connect(lambda _value: self._scroll_to_bottom())
        bubble.height_anim.finished.connect(self._scroll_to_bottom)
        self._schedule_auto_scroll()

    def _build_bubble_row(self, role, bubble):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        if role == "user":
            row_layout.addStretch()
            row_layout.addWidget(bubble, 0, Qt.AlignRight)
        else:
            row_layout.addWidget(bubble, 0, Qt.AlignLeft)
            row_layout.addStretch()
        return row

    def _extract_speakable_length(self, text):
        last_match = None
        for match in re.finditer(r"[.!?](?:\s|$)", str(text or "")):
            last_match = match
        return last_match.end() if last_match else 0

    def _begin_streaming_ai_response(self, initial_text=""):
        if self.streaming_ai_bubble is None:
            self.streaming_ai_bubble = ChatBubble("ai", initial_text or "...")
            self.streaming_ai_row = self._build_bubble_row("ai", self.streaming_ai_bubble)
            index = max(0, self.chat_layout.count() - 1)
            self.chat_layout.insertWidget(index, self.streaming_ai_row)
            self.chat_container.adjustSize()
            self.chat_container.updateGeometry()
            self.scroll.viewport().update()
            self.update()
            self.streaming_ai_bubble.height_anim.valueChanged.connect(lambda _value: self._scroll_to_bottom())
            self.streaming_ai_bubble.height_anim.finished.connect(self._scroll_to_bottom)
        self._schedule_auto_scroll()

    def _update_streaming_ai_response(self, response_text):
        self._begin_streaming_ai_response(response_text)
        self.streaming_ai_text = str(response_text)
        self.streaming_ai_bubble.set_message(self.streaming_ai_text)
        self.chat_container.adjustSize()
        self.chat_container.updateGeometry()
        self.scroll.viewport().update()
        self.update()
        self._schedule_auto_scroll()

        speak_upto = self._extract_speakable_length(self.streaming_ai_text)
        if speak_upto > self.streaming_tts_index:
            segment = self.streaming_ai_text[self.streaming_tts_index:speak_upto].strip()
            self.streaming_tts_index = speak_upto
            if segment:
                self._speak_async(segment)

    def _finish_streaming_ai_response(self, final_text):
        text = str(final_text or "").strip()
        if self.streaming_ai_bubble is not None:
            self.streaming_ai_bubble.set_message(text or "...")
            self.chat_container.adjustSize()
            self.chat_container.updateGeometry()
            self._schedule_auto_scroll()

        if text:
            tail = text[self.streaming_tts_index:].strip()
            if tail:
                self._speak_async(tail)
        elif self.streaming_ai_bubble is None:
            self._append_bubble("ai", "")

        self.streaming_ai_text = ""
        self.streaming_tts_index = 0
        self.streaming_ai_bubble = None
        self.streaming_ai_row = None

    def _schedule_auto_scroll(self):
        for delay in (0, 30, 70, 120, 180, 260):
            QTimer.singleShot(delay, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _run_on_ui_thread(self, fn):
        if QThread.currentThread() == self.thread():
            return fn()

        done = threading.Event()
        result = {}

        def wrapper():
            try:
                result["value"] = fn()
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        self.ui_task_signal.emit(wrapper)
        done.wait()

        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _speak_async(self, text):
        def runner():
            try:
                speak(str(text))
            except Exception:
                pass

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

    def _execute_ui_callable(self, callback):
        try:
            callback()
        except Exception:
            pass

    def _set_busy(self, busy):
        self.input_field.setDisabled(busy)
        self.send_btn.setDisabled(busy)
        self.background_btn.setDisabled(busy)
        if hasattr(self, "test_voice_btn"):
            self.test_voice_btn.setDisabled(busy)

    def _start_typing(self, text="Winter is thinking"):
        self.typing_step = 0
        self._typing_base = text

        if self.typing_timer.isActive():
            self.typing_timer.stop()

        self.typing_timer.timeout.connect(self._tick_typing)
        self.typing_timer.start(250)
        self._tick_typing()

    def _tick_typing(self):
        dots = "." * (self.typing_step % 4)
        self.typing_label.setText(f"{self._typing_base}{dots}")
        self.typing_step += 1

    def _stop_typing(self):
        try:
            self.typing_timer.timeout.disconnect(self._tick_typing)
        except Exception:
            pass
        self.typing_timer.stop()
        self.typing_label.setText("")

    def process_input(self):
        if self.command_worker is not None and self.command_worker.isRunning():
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self._append_bubble("user", text)
        self.input_field.clear()

        if self._handle_ui_control_commands(text):
            return

        if not self.backend_active:
            self.display_response("Backend is paused. Resume it to continue.")
            return

        self._run_backend_command(text)

    def display_response(self, response):
        self._append_bubble("ai", response)
        self._speak_async(response)

    def _confirm_action(self, prompt):
        def ask():
            reply = QMessageBox.question(
                self,
                "Confirm Action",
                str(prompt),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return reply == QMessageBox.Yes

        return bool(self._run_on_ui_thread(ask))

    def _run_backend_command(self, command_text):
        self._set_busy(True)
        self._start_typing(self._persona_text("typing_thinking", "Winter is thinking"))
        self.streaming_ai_text = ""
        self.streaming_tts_index = 0
        self.streaming_ai_bubble = None
        self.streaming_ai_row = None

        self.command_worker = CommandWorker(command_text)
        if self.command_worker is not None:
            self.command_worker.partial.connect(self._on_command_partial, Qt.QueuedConnection)
            self.command_worker.finished.connect(self._on_command_finished, Qt.QueuedConnection)
            self.command_worker.failed.connect(self._on_command_failed, Qt.QueuedConnection)
            self.command_worker.finished.connect(self.command_worker.deleteLater)
            self.command_worker.failed.connect(self.command_worker.deleteLater)
            self.command_worker.start()

    def _on_command_partial(self, response_text):
        self._update_streaming_ai_response(response_text)

    def _on_command_finished(self, response):
        self.command_worker = None
        self._stop_typing()
        final_text = str(response or "").strip()
        if self.streaming_ai_bubble is not None:
            self._finish_streaming_ai_response(final_text)
        elif final_text:
            self.display_response(final_text)
        self._set_busy(False)
        self._handle_suggestions()

    def _on_command_failed(self, error_text):
        self.command_worker = None
        self._stop_typing()
        self.streaming_ai_text = ""
        self.streaming_tts_index = 0
        self.streaming_ai_bubble = None
        self.streaming_ai_row = None
        self.display_response(error_text)
        self._set_busy(False)

    def _handle_suggestions(self):
        actions = get_action_suggestions()
        if not actions:
            return

        for action in actions:
            message = action.get("message", "Suggestion available")
            self._append_bubble("ai", message)
            self._speak_async(message)

            choice = QMessageBox.question(
                self,
                "Suggestion",
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if choice != QMessageBox.Yes:
                skip_message = "Action skipped."
                self._append_bubble("ai", skip_message)
                self._speak_async(skip_message)
                continue

            action_type = action.get("type", "")
            self._run_action(action_type)

    def _run_action(self, action_type):
        if self.action_worker is not None and self.action_worker.isRunning():
            return

        self._set_busy(True)
        self._start_typing(self._persona_text("typing_action", "Winter is processing action"))

        self.action_worker = ActionWorker(action_type)
        if self.action_worker is not None:
            self.action_worker.finished.connect(self._on_action_finished, Qt.QueuedConnection)
            self.action_worker.failed.connect(self._on_action_failed, Qt.QueuedConnection)
            self.action_worker.finished.connect(self.action_worker.deleteLater)
            self.action_worker.failed.connect(self.action_worker.deleteLater)
            self.action_worker.start()

    def _on_action_finished(self, result):
        self.action_worker = None
        self._stop_typing()
        self._append_bubble("ai", result)
        self._speak_async(result)
        self._set_busy(False)

    def _on_action_failed(self, error_text):
        self.action_worker = None
        self._stop_typing()
        self._append_bubble("ai", error_text)
        self._set_busy(False)

    def enable_background_mode(self):
        if self.background_voice_worker is None or not self.background_voice_worker.isRunning():
            self.background_voice_worker = BackgroundVoiceWorker(
                inactivity_seconds=60,
                voice_copy=self._persona_voice_copy(),
            )
            self.background_voice_worker.status.connect(self._on_background_status, Qt.QueuedConnection)
            self.background_voice_worker.activated.connect(self._on_wake_activated, Qt.QueuedConnection)
            self.background_voice_worker.deactivated.connect(self._on_wake_deactivated, Qt.QueuedConnection)
            self.background_voice_worker.command_heard.connect(self._on_background_command, Qt.QueuedConnection)
            self.background_voice_worker.response_ready.connect(self._on_background_response, Qt.QueuedConnection)
            self.background_voice_worker.start()
        else:
            self.background_voice_worker.set_voice_copy(self._persona_voice_copy())

        self._append_bubble("ai", self._persona_text("background_enabled", "Background mode enabled. App minimized. Say 'Hey Winter' to activate."))
        self._set_status_waiting(self._persona_text("wake_waiting", "Wake Waiting"))
        self.showMinimized()

    def _on_background_status(self, text):
        self._append_bubble("ai", text)
        self._update_tray_status(text)

    def _on_wake_activated(self):
        msg = self._persona_text("wake_notice", "Wake word detected. Winter activated and ready.")
        self._append_bubble("ai", msg)
        active_text = self._persona_text("wake_active", "Wake Active")
        self._set_status_active(active_text)
        self._update_tray_status(active_text)

    def _on_wake_deactivated(self, text):
        self._append_bubble("ai", text)
        waiting_text = self._persona_text("wake_waiting", "Wake Waiting")
        self._set_status_waiting(waiting_text)
        self._update_tray_status(waiting_text)

    def _on_background_command(self, command_text):
        self._append_bubble("user", command_text)

    def _on_background_response(self, response):
        self._append_bubble("ai", response)

    def _set_status_active(self, text):
        self.status_chip.setText(text)
        self._update_tray_status(text)
        accent = str(self._current_persona().get("accent", "#00f5ff"))
        accent_rgb = accent.lstrip("#")
        r, g, b = int(accent_rgb[0:2], 16), int(accent_rgb[2:4], 16), int(accent_rgb[4:6], 16)
        self.status_chip.setStyleSheet(
            f"""
            QLabel {{
                background: rgba({r}, {g}, {b}, 26);
                color: {accent};
                border-radius: 9px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            """
        )

    def _set_status_waiting(self, text):
        self.status_chip.setText(text)
        self._update_tray_status(text)
        self.status_chip.setStyleSheet(
            """
            QLabel {
                background: rgba(147, 0, 10, 0.25);
                color: #ffb4ab;
                border-radius: 9px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )

    def _select_file_option(self, matches, target_text):
        def ask():
            title = "Select File"
            prompt = f"Multiple matches found for: {target_text}"
            selected, ok = QInputDialog.getItem(self, title, prompt, [str(item) for item in matches], 0, False)
            if not ok:
                return None

            try:
                return matches.index(selected)
            except ValueError:
                return None

        return self._run_on_ui_thread(ask)

    def _next_unique_export_path(self, candidate_path):
        base, ext = os.path.splitext(candidate_path)
        if not os.path.exists(candidate_path):
            return candidate_path

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base}_{stamp}{ext}"

    def _read_env_value(self, key, default=""):
        try:
            if not os.path.exists(ENV_FILE):
                return str(default)
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith(f"{key}="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return value
        except Exception:
            return str(default)
        return str(default)

    def _write_env_values(self, updates):
        # 1. Update the process environment immediately
        for key, val in updates.items():
            os.environ[key] = str(val)
            print(f"[ENV] os.environ['{key}'] = '{val}'")

        # 2. Update the .env file with a robust dict-driven swap
        env_data = {}
        if os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and "=" in line and not line.startswith("#"):
                            fk, fv = line.split("=", 1)
                            env_data[fk.strip()] = fv.strip().strip('"').strip("'")
            except Exception:
                pass

        # Apply updates to our dict
        for key, val in updates.items():
            env_data[key] = str(val)

        # Write everything back
        try:
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                for ek, ev in env_data.items():
                    f.write(f'{ek}="{ev}"\n')
            print(f"[ENV] .env file written successfully with {len(env_data)} keys")
        except Exception as e:
            print(f"[ENV] Error writing .env file: {e}")

    def test_tts_voice(self):
        character = self.tts_character_combo.currentText().strip()

        if self.voice_preview_worker is not None and self.voice_preview_worker.isRunning():
            return

        import random
        samples = [
            "Hello boss. Testing identity now. Kya meri awaaz saaf aa rahi hai?",
            "Namaste, main aapka AI assistant hoon. Test preview shuru kar rahi hoon.",
            "Testing my voice settings. Main Hindi aur English dono mein baat kar sakti hoon.",
            "Boss, naya voice profile check kijiye. Sab theek lag raha hai na?",
            "Voice test in progress. Main aapke har sawal ka jawab dene ke liye taiyaar hoon.",
            "Arre boss, suniye! Yeh voice kaisi lag rahi hai aapko?",
            "Checking local neural engine. Clear sound quality test performed.",
            "Aapka naya voice character set ho chuka hai. Chaliye ab koi kaam karte hain."
        ]
        sample = random.choice(samples)
        self._append_bubble("ai", f"Testing identity '{character}' now. If local, downloading may take a moment...")
        self._set_busy(True)
        self._start_typing(f"Testing {character}")
        self.voice_preview_worker = VoicePreviewWorker(
            text=sample,
            character=character,
        )
        self.voice_preview_worker.finished.connect(self._on_voice_preview_finished, Qt.QueuedConnection)
        self.voice_preview_worker.failed.connect(self._on_voice_preview_failed, Qt.QueuedConnection)
        self.voice_preview_worker.finished.connect(self.voice_preview_worker.deleteLater)
        self.voice_preview_worker.failed.connect(self.voice_preview_worker.deleteLater)
        self.voice_preview_worker.start()

    def _on_voice_preview_finished(self, message):
        self.voice_preview_worker = None
        self._stop_typing()
        self._set_busy(False)
        self._append_bubble("ai", message)

    def _on_voice_preview_failed(self, error_text):
        self.voice_preview_worker = None
        self._stop_typing()
        self._set_busy(False)
        self._append_bubble("ai", error_text)

    def export_memory_from_ui(self):
        default_name = f"winter_memory_{datetime.now().strftime('%Y%m%d')}"
        selected, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Memory",
            default_name,
            "PDF Files (*.pdf);;DOC Files (*.doc)",
        )
        if not selected:
            return

        if selected.lower().endswith(".pdf") or "PDF" in selected_filter:
            fmt = "pdf"
            if not selected.lower().endswith(".pdf"):
                selected = f"{selected}.pdf"
        else:
            fmt = "doc"
            if not selected.lower().endswith(".doc"):
                selected = f"{selected}.doc"

        final_path = self._next_unique_export_path(selected)
        result = export_memory_history(export_format=fmt, output_path=final_path)
        QMessageBox.information(self, "Memory Export", result)

    def show_memory_insights(self):
        insights = get_memory_insights()
        prefs = insights.get("preferences", {})

        text = (
            "Memory Insights\n\n"
            f"Short-term chats: {insights.get('short_term_count', 0)}\n"
            f"Pending for summary: {insights.get('pending_for_summary', 0)}\n"
            f"Long-term summaries: {insights.get('summary_count', 0)}\n"
            f"Archived chat count: {insights.get('total_archived_chats', 0)}\n"
            f"Active persona: {get_persona_meta(prefs.get('assistant_persona', 'balanced')).get('label', 'Balanced')}\n"
            f"Top language trend: {insights.get('top_language', 'n/a')}\n"
            f"Top style trend: {insights.get('top_style', 'n/a')}\n"
            f"Top workflow trend: {insights.get('top_workflow', 'n/a')}\n"
            f"Friend-tone score: {insights.get('friend_tone_score', 0)}\n\n"
            "Preference Locks\n"
            f"Persona: {prefs.get('assistant_persona', 'balanced')}\n"
            f"Language: {prefs.get('preferred_language', 'auto')}\n"
            f"Tone: {prefs.get('preferred_tone', 'auto')}\n"
            f"Response length: {prefs.get('preferred_response_length', 'auto')}\n"
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Memory Insights")
        dialog.resize(520, 420)
        layout = QVBoxLayout(dialog)

        box = QTextEdit()
        box.setReadOnly(True)
        box.setText(text)
        layout.addWidget(box)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec_()

    def _update_persona_description(self, persona_id):
        persona = get_persona_meta(persona_id)
        self.persona_description.setText(
            f"{persona.get('label', 'Balanced')}: {persona.get('description', '')}"
        )

    def save_persona_preset(self):
        persona_id = normalize_persona_id(self.persona_preset_combo.currentText())
        set_user_preferences({"assistant_persona": persona_id})
        self._apply_persona_visuals(persona_id)
        self._append_bubble(
            "ai",
            f"Persona switched to {get_persona_meta(persona_id).get('label', 'Balanced')}.",
        )

    def open_persona_settings(self):
        current = get_user_preferences()

        dialog = QDialog(self)
        dialog.setWindowTitle("Persona Settings")
        dialog.resize(420, 260)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()

        persona_combo = QComboBox()
        persona_combo.addItems(get_persona_options())
        persona_combo.setCurrentText(
            normalize_persona_id(current.get("assistant_persona", "balanced"))
        )

        language_combo = QComboBox()
        language_combo.addItems(["auto", "english", "hindi", "hinglish"])
        language_combo.setCurrentText(current.get("preferred_language", "auto"))

        tone_combo = QComboBox()
        tone_combo.addItems(["auto", "friend-like", "professional-friendly"])
        tone_combo.setCurrentText(current.get("preferred_tone", "auto"))

        length_combo = QComboBox()
        length_combo.addItems(["auto", "short", "detailed"])
        length_combo.setCurrentText(current.get("preferred_response_length", "auto"))

        form.addRow("AI Persona", persona_combo)
        form.addRow("Preferred Language", language_combo)
        form.addRow("Preferred Tone", tone_combo)
        form.addRow("Response Length", length_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def on_save():
            set_user_preferences(
                {
                    "assistant_persona": persona_combo.currentText(),
                    "preferred_language": language_combo.currentText(),
                    "preferred_tone": tone_combo.currentText(),
                    "preferred_response_length": length_combo.currentText(),
                }
            )
            self.persona_preset_combo.setCurrentText(
                normalize_persona_id(persona_combo.currentText())
            )
            self._apply_persona_visuals(self.persona_preset_combo.currentText())
            dialog.accept()
            self._append_bubble("ai", "Persona preferences saved.")

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def save_live_web_settings(self):
        set_user_preferences(
            {
                "live_web_access": self.live_web_toggle.isChecked(),
                "web_search_mode": self.web_mode_combo.currentText().strip().lower(),
                "preferred_news_region": self.news_region_combo.currentText().strip().lower(),
                "preferred_news_language": self.news_language_combo.currentText().strip().lower(),
            }
        )
        state_text = "ON" if self.live_web_toggle.isChecked() else "OFF"
        self._append_bubble(
            "ai",
            (
                "Live web settings saved. "
                f"Access: {state_text}, mode: {self.web_mode_combo.currentText()}, region: {self.news_region_combo.currentText().upper()}, "
                f"language: {self.news_language_combo.currentText()}."
            ),
        )

    def save_tts_settings(self, text=None):
        character = self.tts_character_combo.currentText().strip()

        self._write_env_values(
            {
                "TTS_CHARACTER": character,
            }
        )
        reset_tts_backend()
        self._append_bubble(
            "ai",
            (
                f"Voice settings saved to '{character}'. "
                "New identity will be used on the next spoken response."
            ),
        )

    def reset_persona_from_ui(self):
        confirm = QMessageBox.question(
            self,
            "Reset Persona",
            "Reset persona learning and preference locks? This will NOT delete memory history.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        reset_user_profile_learning()
        self._append_bubble("ai", "Persona learning reset done. Memory history is kept safe.")

    def _handle_ui_control_commands(self, text):
        lowered = str(text).strip().lower()

        if lowered in {"sleep", "sleep mode", "pause", "pause backend"}:
            if self.backend_active:
                self.toggle_backend(force_state=False)
                self.display_response("Backend paused.")
            else:
                self.display_response("Backend already paused.")
            return True

        if lowered in {"wake", "wake up", "resume", "start backend"}:
            if not self.backend_active:
                self.toggle_backend(force_state=True)
                self.display_response("Backend resumed.")
            else:
                self.display_response("Backend already active.")
            return True

        if lowered in {"exit", "quit", "close app", "shutdown"}:
            self.close()
            return True

        return False

    def toggle_backend(self, force_state=None):
        if force_state is None:
            self.backend_active = not self.backend_active
        else:
            self.backend_active = bool(force_state)

        if self.backend_active:
            self._set_status_active(self._persona_text("status_active", "Backend Active"))
            self.backend_toggle_btn.setText("Pause")
        else:
            self._set_status_waiting(self._persona_text("status_waiting", "Backend Paused"))
            self.backend_toggle_btn.setText("Resume")

    def closeEvent(self, event):
        clear_confirm_handler()
        clear_file_selection_handler()

        if self.command_worker is not None and self.command_worker.isRunning():
            self.command_worker.quit()
            self.command_worker.wait(1000)

        if self.action_worker is not None and self.action_worker.isRunning():
            self.action_worker.quit()
            self.action_worker.wait(1000)

        if self.voice_preview_worker is not None and self.voice_preview_worker.isRunning():
            self.voice_preview_worker.quit()
            self.voice_preview_worker.wait(1000)

        if self.background_voice_worker is not None and self.background_voice_worker.isRunning():
            self.background_voice_worker.stop()
            self.background_voice_worker.wait(1500)

        if self.tray_icon is not None:
            self.tray_icon.hide()

        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = AIAssistantUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
