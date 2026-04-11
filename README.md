# Project Winter: Desktop AI Assistant

Winter is a premium desktop AI assistant built with PyQt5 + Groq LLM integration. It features high-fidelity voice output, multi-engine Hindi TTS, and a modern, glassmorphism-inspired dark UI.

---

## 📸 Interface Showcase

<p align="center">
  <img src="assets/ui_chat.png" width="48%" alt="Chat Interface" />
  <img src="assets/ui_settings.png" width="48%" alt="Settings Panel" />
</p>

<p align="center">
  <b>Advanced Voice Selection</b><br/>
  <img src="assets/voice_dropdown.png" width="97%" alt="Voice Selection" />
</p>

---

## 🚀 Recent Modifications

### 🎙️ Enhanced Multi-Engine TTS (Hindi/Hinglish)
- **Categorized Voice Selection**: Organized by origin and quality (☁️ Cloud, 🎙️ Local HD, ⚡ Fast Local).
- **Improved Hindi Phrasing**: Integrated **Google TTS (Divya)** and **Microsoft Edge Neural** for natural pronunciation.
- **Dynamic Voice Testing**: Randomized Hindi/English phrases for realistic character previews.

### 🧠 Core Improvements
- **Unicode Support**: Crystal-clear Devanagari display with total UTF-8 stream synchronization.
- **Smooth Animations**: Thread-safe UI updates for seamless bubble rendering.
- **Project Sanitization**: Removed all legacy temporary scripts and test binaries.

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
- `src/utils/voice.py`: STT/TTS Manager & Engines (Edge, Piper, Kokoro, gTTS).

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
- *"Latest tech news batao"* (Web-augmented search)
- *"Organize my downloads"* (File automation)
- *"Kya scene hai? Kaise ho?"* (Natural conversation)
- *"Naya folder banao Desktop pe"* (System control)
