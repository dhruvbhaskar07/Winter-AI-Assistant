# Project Winter: Desktop AI Assistant

Winter is a premium desktop AI assistant built with PyQt5 + Groq LLM integration. It features high-fidelity voice output, multi-engine Hindi TTS, and a modern, glassmorphism-inspired dark UI.

---

## 📸 Interface Showcase

<table border="0">
  <tr>
    <td><img src="assets/ui_chat.png" width="100%" alt="Clean Chat Experience" /></td>
    <td><img src="assets/ui_settings.png" width="100%" alt="Advanced Settings" /></td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <b>Advanced Voice Identity Selector</b><br/>
      <img src="assets/voice_dropdown.png" width="100%" alt="Categorized Voices" />
    </td>
  </tr>
</table>

---

## 🚀 Key Features & Updates

### 🎙️ Multi-Engine Hindi TTS
- **Categorized Selection**: Cloud, Local HD, and Fast Local voice types.
- **Natural Phrasing**: Integrated Google TTS & Edge Neural for perfect Hindi/Hinglish.
- **Dynamic Previews**: Randomized phrases to test character tone and clarity.

### 🧠 Intelligent Core
- **Unicode Support**: Total UTF-8 synchronization for clean Devanagari (Hindi) text.
- **Async Processing**: Thread-safe UI updates for smooth chat bubble rendering.
- **Minimalist Footprint**: Fully sanitized project structure with zero clutter.

## 🏗️ Project Structure

### Root
- `ui.py`: Desktop UI entry point.
- `main.py`: Voice/CLI entry point.
- `requirements.txt`: Python dependencies.
- `.env`: Runtime configuration.

### Core (`src/`)
- `src/ui_app.py`: Main PyQt5 UI & worker orchestrator.
- `src/modules/command_handler.py`: Intent routing + AI/web coordination.
- `src/services/llm_service.py`: UTF-8 Stream handler & LLM logic.
- `src/utils/voice.py`: Full STT/TTS Backend management.

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

Copy `.env.example` to `.env` and set your `API_KEY`.
