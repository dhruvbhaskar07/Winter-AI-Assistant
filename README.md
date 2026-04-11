# Project Winter: Desktop AI Assistant

Winter is a premium desktop AI assistant built with PyQt5 + Groq LLM integration. It features high-fidelity voice output, multi-engine Hindi TTS, and a modern, glassmorphism-inspired dark UI.

## 🚀 Recent Modifications

### 🎙️ Enhanced Multi-Engine TTS (Hindi/Hinglish)
- **Categorized Voice Selection**: Voices are now organized by origin and quality:
  - **☁️ Cloud Voices**: High-fidelity Microsoft Edge and Google TTS models.
  - **🎙️ Local HD Voices**: High-definition Piper neural voices (Work 100% offline).
  - **⚡ Fast Local Voices**: Lightweight Kokoro models optimized for speed.
  - **💾 Legacy Voices**: Backward compatibility for older ONNX models.
- **Improved Hindi Phrasing**: Integrated **Google TTS (Divya)** for exceptionally natural Hinglish and proper Hindi pronunciation.
- **Dynamic Voice Testing**: "Test Identity" now uses randomized Hindi/English phrases to give a realistic preview of the character's tone.

### 🧠 Core Improvements
- **Unicode Support**: Fixed a critical text streaming bug where Hindi characters and punctuation were corrupted. Stream now uses forced UTF-8 encoding for crystal-clear Devanagari display.
- **Smooth Animations**: Refined UI thread handling to ensure chat bubbles and autoscroll work seamlessly during intensive AI thinking/speaking.

## 📸 Media Showcase

*Winter AI - Modern Chat Experience*
![Winter UI Chat](assets/ui_chat.png)

*Advanced Settings & Voice Profiling*
![Winter UI Settings](assets/ui_settings.png)

*Categorized Voice Identity Selector*
![Voice Dropdown](assets/voice_dropdown.png)

---

## 🏗️ Project Structure

### Root
- `ui.py`: Desktop UI entry point.
- `main.py`: Voice/CLI entry point.
- `requirements.txt`: Python dependencies.
- `.env`: Runtime configuration.

### Core (`src/`)
- `src/ui_app.py`: Main PyQt5 UI, workers, and chat rendering.
- `src/modules/command_handler.py`: Intent routing + AI/web orchestration.
- `src/services/llm_service.py`: Groq API, System Prompts, and UTF-8 Stream handler.
- `src/utils/voice.py`: STT/TTS Manager & Multiple Engine Backends (Edge, Piper, Kokoro, gTTS).

## 🛠️ Setup & Installation

### 1) Quick Setup Scripts
- **Windows**: `scripts/1_WINDOWS_SETUP.bat`
- **Linux/macOS**: `bash scripts/2_LINUX_SETUP.sh`

### 2) Manual Installation
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure your `API_KEY`.

## 🧪 Example Commands
- *"Latest tech news batao"* (Triggers web-augmented search)
- *"Organize my downloads"* (Launches file automation)
- *"Kya scene hai? Kaise ho?"* (Natural conversational mode)
- *"Naya folder banao Desktop pe"* (System control)

## 🔧 Troubleshooting
- **Hindi Layout Issues**: Ensure your system font supports Devanagari (Roboto/Inter recommended).
- **Voice Lag**: For local voices, the first use triggers a one-time download (~20-50MB).
- **HTTP 403 (Edge TTS)**: The system automatically falls back to **Google TTS** if Microsoft Edge is blocked by your ISP/Network.
