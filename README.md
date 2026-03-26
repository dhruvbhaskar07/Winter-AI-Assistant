# ❄️ Project Winter: The Modular Desktop AI Assistant

![Winter AI Hero Banner](assets/winter_ai_hero.png)

> **"A warm, friend-like, and practical voice assistant that lives on your desktop, learns your habits, and automates your workflow."**

---

## 🌟 Overview

**Winter AI** is a state-of-the-art modular desktop assistant designed for personal productivity and automation. Unlike generic chatbots, Winter is deep-integrated into your local system, offering native voice control, a stunning **glassmorphism UI**, and an **advanced memory system** that evolves with you. 

Built with **Llama 3 & 3.3 models** via Groq, Winter combines lightning-fast intelligence with high-fidelity voice interaction using **Google STT** and **Edge TTS**.

---

## 🚀 Key Features

### 🎧 Natural Voice Interaction
*   **Native Wake Word**: Activated with "Hey Winter" (or "Hi Winter", "A Winter").
*   **Hinglish Support**: Naturally understands and responds in Hindustani (Hinglish).
*   **Edge-Quality TTS**: Uses Microsoft’s premium Edge TTS for smooth, human-like speech.
*   **Adaptive Listening**: Multi-profile STT (Near/Far/Balanced) to work in any environment.

### 🖼️ Next-Gen PyQt5 Interface
*   **Glassmorphism UX**: Modern dark-mode UI with translucent panels and smooth animations.
*   **Tray Integration**: Runs quietly in the background; restores instantly from the system tray.
*   **Live Chat Feed**: Responsive chat bubbles with typing indicators and real-time status chips.

### 🧠 Advanced Memory & Learning
*   **Inferred Personalization**: Learns your language taste, response style (short/detailed), and workflow focus without any manual setup.
*   **Long-Term Archive**: Automatically summarizes conversations into a local SQLite database.
*   **History Export**: Export your entire memory and chat history to **PDF** or **DOC** files.

### 🛠️ Intelligent System Control
*   **Smart File Search**: High-performance local search with scoring/ranking logic (includes OneDrive support).
*   **Compound Commands**: Supports multi-step tasks like *"Open Chrome and then organize my downloads folder"*.
*   **Proactive Suggestions**: Detects repetitive tasks or cluttered folders and suggests automation actions.
*   **Safety Guards**: Critical system changes require your explicit voice or UI confirmation.

---

## 📂 Project Architecture & File Analysis

The project follows a modular, scalable architecture separating core services, automation logic, and UI components.

### 📁 Root Directory
*   `ui.py`: The primary entry point for the **Desktop GUI Mode**.
*   `main.py`: The entry point for the **Voice/CLI Mode**.
*   `requirements.txt`: Manages all Python dependencies (PyQt5, edge-tts, Groq, etc.).
*   `.env`: Secure storage for your Groq API Key and customization variables.

### 📁 `src/` - The Core Engine
*   `ui_app.py`: Contains the 1,000+ line PyQt5 implementation. Handles animations, threads, and real-time state management.
*   `cli_main.py`: Logic for the command-line interface, including the wake-word loop and background workers.

#### 📁 `src/modules/` - Feature Implementation
*   `automation.py`: Logic for organizing the Downloads folder, creating directories, and renaming files.
*   `command_handler.py`: The **Brain Router**. Uses LLM intent detection to route user requests to the correct subsystem. Supports regex-based rule-matching for speed and LLM for complex queries.
*   `system_control.py`: OS-level interaction (opening apps, launching files with default handlers).

#### 📁 `src/services/` - External Integrations
*   `llm_service.py`: Interfaces with Groq API. Contains custom system prompts for "Winter's" persona and intent extraction logic.

#### 📁 `src/utils/` - Utility & Logic Layer
*   `memory.py`: Advanced JSON/SQLite storage system. Handles profile learning, context retrieval, and history exporting.
*   `voice.py`: Complex audio handling. Manages the speak/listen threading, STT normalization, and Hinglish romanization.
*   `file_search.py`: Implements a ranked search engine with fuzzy matching and path traversal.
*   `wake_word.py`: Handles wake-word recognition variants and generates AI acknowledgments.
*   `decision_engine.py`: Evaluates the "risk" of suggested actions before presenting them to the user.
*   `safety.py`: Global confirmation handler for dangerous operations.

---

## 🛠️ Installation & Setup

### 1️⃣ One-Click Setup (Recommended)
Navigate to the `scripts/` folder and run the launcher for your OS:
*   **Windows**: Double-click `scripts/1_WINDOWS_SETUP.bat`
*   **Linux/macOS**: Run `bash scripts/2_LINUX_SETUP.sh`

### 2️⃣ Manual Setup
1.  **Clone & Enter**:
    ```powershell
    git clone <your-repo-url>
    cd AI
    ```
2.  **Venv & Deps**:
    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```
3.  **Config**:
    Copy `.env.example` to `.env` and add your `API_KEY`.

---

## ⚙️ Environment Variables

Configure your `.env` for the best experience:
*   `API_KEY`: Your Groq API Key (Required).
*   `ASSISTANT_NAME`: Default is "Winter".
*   `LLM_MODEL`: e.g., `llama-3.3-70b-versatile`.
*   `STT_PROFILE`: `near`, `far`, or `balanced`.

---

## 📄 Notes & Troubleshooting
*   **Runtime Data**: Conversation history and learned commands are stored in `data/` (Auto-generated).
*   **Audio Issues**: If `PyAudio` fails on Windows, use `pip install pipwin` followed by `pipwin install pyaudio`.
*   **Hinglish**: Winter is optimized for natural code-switching between English and Hindi. Try saying *"Winter, desktop pe ek Galaxy folder bana do"*.

---

<p align="center">
  Built with ❤️ for <b>WinterOS</b>
</p>
