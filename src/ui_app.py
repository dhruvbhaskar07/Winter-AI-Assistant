import sys
import threading
import time
from datetime import datetime
import os

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
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
    set_file_selection_handler,
)
from utils.safety import clear_confirm_handler, set_confirm_handler
from utils.suggestions import get_action_suggestions
from utils.voice import listen, speak
from utils.memory import (
    export_memory_history,
    get_memory_insights,
    get_user_preferences,
    reset_user_profile_learning,
    set_user_preferences,
)


class CommandWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, command_text):
        super().__init__()
        self.command_text = command_text

    def run(self):
        try:
            response = handle_command(self.command_text)
            self.finished.emit(str(response))
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


class BackgroundVoiceWorker(QThread):
    status = pyqtSignal(str)
    activated = pyqtSignal()
    deactivated = pyqtSignal(str)
    command_heard = pyqtSignal(str)
    response_ready = pyqtSignal(str)

    def __init__(self, inactivity_seconds=60):
        super().__init__()
        self.inactivity_seconds = max(10, int(inactivity_seconds))
        self._running = True
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
        self.status.emit("Background mode on. Say 'Hey Winter' to activate.")
        speak("Background mode enabled. Say Hey Winter to activate me.")

        while self._running:
            if active and (time.time() - last_command_at) >= self.inactivity_seconds:
                active = False
                msg = "No command for 1 minute. Winter inactive now. Say Hey Winter to activate again."
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
                    speak("Winter activated. I am ready for your commands.")
                continue

            if self._is_sleep(heard):
                active = False
                msg = "Winter sleeping. Say Hey Winter to activate again."
                self.deactivated.emit(msg)
                speak(msg)
                continue

            if self._is_wake(heard):
                speak("I am active and listening.")
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        role_text = "You" if role == "user" else "Winter"
        role_label = QLabel(role_text)
        role_label.setStyleSheet(
            "color: #93c5fd; font-size: 11px; font-weight: 600;"
            if role == "user"
            else "color: #86efac; font-size: 11px; font-weight: 600;"
        )

        message_label = QLabel(str(message))
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        message_label.setStyleSheet("color: #e5e7eb; font-size: 14px;")

        layout.addWidget(role_label)
        layout.addWidget(message_label)

        if role == "user":
            self.setStyleSheet(
                """
                #bubble {
                    background-color: rgba(37, 99, 235, 145);
                    border: 1px solid rgba(96, 165, 250, 90);
                    border-radius: 14px;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                #bubble {
                    background-color: rgba(30, 41, 59, 220);
                    border: 1px solid rgba(148, 163, 184, 45);
                    border-radius: 14px;
                }
                """
            )

        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.opacity.setOpacity(0.0)

        self.opacity_anim = QPropertyAnimation(self.opacity, b"opacity", self)
        self.opacity_anim.setDuration(220)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.height_anim = QPropertyAnimation(self, b"maximumHeight", self)
        self.height_anim.setDuration(240)
        self.height_anim.setEasingCurve(QEasingCurve.OutCubic)

        QTimer.singleShot(0, self.play_animation)

    def play_animation(self):
        target = self.sizeHint().height() + 8
        self.height_anim.setStartValue(0)
        self.height_anim.setEndValue(target)
        self.height_anim.start()
        self.opacity_anim.start()


class AIAssistantUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Winter AI")
        self.resize(1080, 720)

        self.command_worker = None
        self.action_worker = None
        self.background_voice_worker = None

        self.backend_active = True
        self.typing_timer = QTimer(self)
        self.typing_step = 0
        self.tray_icon = None
        self.tray_menu = None
        self.tray_status_action = None

        self._build_ui()
        self._play_window_intro()
        self._setup_tray()

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
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0b1220;
                color: #e2e8f0;
                font-family: Segoe UI;
            }
            QLineEdit {
                background: rgba(15, 23, 42, 235);
                border: 1px solid rgba(148, 163, 184, 45);
                border-radius: 13px;
                padding: 12px 14px;
                color: #e5e7eb;
                font-size: 14px;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid rgba(148, 163, 184, 40);
                border-radius: 12px;
                padding: 10px 14px;
                color: #e2e8f0;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
            }
            QTabWidget::pane {
                border: 1px solid rgba(148, 163, 184, 35);
                border-radius: 12px;
                margin-top: 6px;
            }
            QTabBar::tab {
                background: rgba(30, 41, 59, 200);
                border: 1px solid rgba(148, 163, 184, 35);
                border-bottom: none;
                min-width: 88px;
                padding: 8px 14px;
                margin-right: 6px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background: rgba(59, 130, 246, 70);
                border-color: rgba(96, 165, 250, 80);
            }
            QGroupBox {
                border: 1px solid rgba(148, 163, 184, 35);
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: 600;
                color: #dbeafe;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #93c5fd;
            }
            """
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        panel = QFrame()
        panel.setStyleSheet(
            """
            QFrame {
                background-color: rgba(15, 23, 42, 220);
                border: 1px solid rgba(148, 163, 184, 35);
                border-radius: 16px;
            }
            """
        )

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Winter AI")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))

        self.status_chip = QLabel("Backend Active")
        self.status_chip.setStyleSheet(
            """
            QLabel {
                background: rgba(16, 185, 129, 35);
                color: #86efac;
                border: 1px solid rgba(16, 185, 129, 90);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )

        self.backend_toggle_btn = QPushButton("Pause")
        self.backend_toggle_btn.clicked.connect(self.toggle_backend)
        self.backend_toggle_btn.setFixedWidth(88)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status_chip)
        header.addWidget(self.backend_toggle_btn)

        self.tabs = QTabWidget()

        chat_tab = QWidget()
        chat_tab_layout = QVBoxLayout(chat_tab)
        chat_tab_layout.setContentsMargins(10, 10, 10, 10)
        chat_tab_layout.setSpacing(10)

        self.typing_label = QLabel("")
        self.typing_label.setStyleSheet("color: #94a3b8; font-size: 12px;")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 9px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 80);
                border-radius: 4px;
                min-height: 24px;
            }
            """
        )

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_container)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message Winter AI...")
        self.input_field.returnPressed.connect(self.process_input)

        self.background_btn = QPushButton("Background")
        self.background_btn.setFixedWidth(114)
        self.background_btn.clicked.connect(self.enable_background_mode)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.process_input)
        self.send_btn.setFixedWidth(74)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.background_btn)
        input_row.addWidget(self.send_btn)

        chat_tab_layout.addWidget(self.typing_label)
        chat_tab_layout.addWidget(self.scroll)
        chat_tab_layout.addLayout(input_row)

        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(12)

        persona_group = QGroupBox("Persona")
        persona_layout = QGridLayout(persona_group)
        persona_layout.setHorizontalSpacing(10)
        persona_layout.setVerticalSpacing(8)

        persona_info = QLabel("Tune language, tone, and response style for adaptive behavior.")
        persona_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        persona_info.setWordWrap(True)

        self.persona_btn = QPushButton("Open Persona Settings")
        self.persona_btn.clicked.connect(self.open_persona_settings)
        self.reset_btn = QPushButton("Reset Persona Learning")
        self.reset_btn.clicked.connect(self.reset_persona_from_ui)

        persona_layout.addWidget(persona_info, 0, 0, 1, 2)
        persona_layout.addWidget(self.persona_btn, 1, 0)
        persona_layout.addWidget(self.reset_btn, 1, 1)

        memory_group = QGroupBox("Memory")
        memory_layout = QGridLayout(memory_group)
        memory_layout.setHorizontalSpacing(10)
        memory_layout.setVerticalSpacing(8)

        memory_info = QLabel("View memory insights and export full memory when needed.")
        memory_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        memory_info.setWordWrap(True)

        self.insights_btn = QPushButton("Open Insights")
        self.insights_btn.clicked.connect(self.show_memory_insights)
        self.export_btn = QPushButton("Export Memory")
        self.export_btn.clicked.connect(self.export_memory_from_ui)

        memory_layout.addWidget(memory_info, 0, 0, 1, 2)
        memory_layout.addWidget(self.insights_btn, 1, 0)
        memory_layout.addWidget(self.export_btn, 1, 1)

        settings_layout.addWidget(persona_group)
        settings_layout.addWidget(memory_group)
        settings_layout.addStretch()

        self.tabs.addTab(chat_tab, "Chat")
        self.tabs.addTab(settings_tab, "Settings")

        panel_layout.addLayout(header)
        panel_layout.addWidget(self.tabs)

        root.addWidget(panel)

    def _play_window_intro(self):
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.window_opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        self.window_opacity_anim.setDuration(340)
        self.window_opacity_anim.setStartValue(0.0)
        self.window_opacity_anim.setEndValue(1.0)
        self.window_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.window_opacity_anim.start()

    def _append_bubble(self, role, message):
        bubble = ChatBubble(role, message)
        index = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(index, bubble)
        QTimer.singleShot(20, self._scroll_to_bottom)

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

        QTimer.singleShot(0, wrapper)
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

    def _set_busy(self, busy):
        self.input_field.setDisabled(busy)
        self.send_btn.setDisabled(busy)
        self.background_btn.setDisabled(busy)

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
        self._start_typing("Winter is thinking")

        self.command_worker = CommandWorker(command_text)
        self.command_worker.finished.connect(self._on_command_finished)
        self.command_worker.failed.connect(self._on_command_failed)
        self.command_worker.finished.connect(self.command_worker.deleteLater)
        self.command_worker.failed.connect(self.command_worker.deleteLater)
        self.command_worker.start()

    def _on_command_finished(self, response):
        self.command_worker = None
        self._stop_typing()
        self.display_response(response)
        self._set_busy(False)
        self._handle_suggestions()

    def _on_command_failed(self, error_text):
        self.command_worker = None
        self._stop_typing()
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
        self._start_typing("Winter is processing action")

        self.action_worker = ActionWorker(action_type)
        self.action_worker.finished.connect(self._on_action_finished)
        self.action_worker.failed.connect(self._on_action_failed)
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
            self.background_voice_worker = BackgroundVoiceWorker(inactivity_seconds=60)
            self.background_voice_worker.status.connect(self._on_background_status)
            self.background_voice_worker.activated.connect(self._on_wake_activated)
            self.background_voice_worker.deactivated.connect(self._on_wake_deactivated)
            self.background_voice_worker.command_heard.connect(self._on_background_command)
            self.background_voice_worker.response_ready.connect(self._on_background_response)
            self.background_voice_worker.start()

        self._append_bubble("ai", "Background mode enabled. App minimized. Say 'Hey Winter' to activate.")
        self._set_status_waiting("Wake Waiting")
        self.showMinimized()

    def _on_background_status(self, text):
        self._append_bubble("ai", text)
        self._update_tray_status(text)

    def _on_wake_activated(self):
        msg = "Wake word detected. Winter activated and ready."
        self._append_bubble("ai", msg)
        self._set_status_active("Wake Active")
        self._update_tray_status("Wake Active")

    def _on_wake_deactivated(self, text):
        self._append_bubble("ai", text)
        self._set_status_waiting("Wake Waiting")
        self._update_tray_status("Wake Waiting")

    def _on_background_command(self, command_text):
        self._append_bubble("user", command_text)

    def _on_background_response(self, response):
        self._append_bubble("ai", response)

    def _set_status_active(self, text):
        self.status_chip.setText(text)
        self._update_tray_status(text)
        self.status_chip.setStyleSheet(
            """
            QLabel {
                background: rgba(16, 185, 129, 35);
                color: #86efac;
                border: 1px solid rgba(16, 185, 129, 90);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )

    def _set_status_waiting(self, text):
        self.status_chip.setText(text)
        self._update_tray_status(text)
        self.status_chip.setStyleSheet(
            """
            QLabel {
                background: rgba(245, 158, 11, 35);
                color: #fcd34d;
                border: 1px solid rgba(245, 158, 11, 90);
                border-radius: 10px;
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
            f"Top language trend: {insights.get('top_language', 'n/a')}\n"
            f"Top style trend: {insights.get('top_style', 'n/a')}\n"
            f"Top workflow trend: {insights.get('top_workflow', 'n/a')}\n"
            f"Friend-tone score: {insights.get('friend_tone_score', 0)}\n\n"
            "Preference Locks\n"
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

    def open_persona_settings(self):
        current = get_user_preferences()

        dialog = QDialog(self)
        dialog.setWindowTitle("Persona Settings")
        dialog.resize(420, 260)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()

        language_combo = QComboBox()
        language_combo.addItems(["auto", "english", "hindi", "hinglish"])
        language_combo.setCurrentText(current.get("preferred_language", "auto"))

        tone_combo = QComboBox()
        tone_combo.addItems(["auto", "friend-like", "professional-friendly"])
        tone_combo.setCurrentText(current.get("preferred_tone", "auto"))

        length_combo = QComboBox()
        length_combo.addItems(["auto", "short", "detailed"])
        length_combo.setCurrentText(current.get("preferred_response_length", "auto"))

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
                    "preferred_language": language_combo.currentText(),
                    "preferred_tone": tone_combo.currentText(),
                    "preferred_response_length": length_combo.currentText(),
                }
            )
            dialog.accept()
            self._append_bubble("ai", "Persona preferences saved.")

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

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
            self._set_status_active("Backend Active")
            self.backend_toggle_btn.setText("Pause")
        else:
            self._set_status_waiting("Backend Paused")
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
