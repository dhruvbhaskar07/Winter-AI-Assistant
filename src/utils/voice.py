import asyncio
import importlib.util
import os
import queue
import re
import sys
import tempfile
import threading
import time
import types
import unicodedata
import uuid
import math
import tarfile
import shutil
import wave
import struct
from pathlib import Path

import requests
from tqdm import tqdm
from dotenv import dotenv_values, load_dotenv

try:
    import speech_recognition as sr
    _SR_IMPORT_ERROR = ""
except Exception as exc:
    sr = None
    _SR_IMPORT_ERROR = str(exc)


SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_ROOT)
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=ENV_FILE)


LANGUAGE_PREFERENCES = ("en-IN", "hi-IN", "en-US")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip().lower()

# ─────────────────────────────────────────────────────────
# ██  VOICE CHARACTER REGISTRY
# ─────────────────────────────────────────────────────────
# Each character maps to a TTS engine + config.
# Engines: "edge" (Microsoft Cloud), "gtts" (Google Cloud),
#          "sherpa" (Local Neural), "piper" (Local High-Def),
#          "kokoro" (Local Kokoro ONNX)
# ─────────────────────────────────────────────────────────

VOICE_CHARACTERS = {
    # ── ☁️ CLOUD VOICES (Internet Required - Best Quality) ──
    "☁️ Swara (Edge Neural, Female)": {
        "engine": "edge",
        "voice": "hi-IN-SwaraNeural",
        "category": "cloud",
    },
    "☁️ Madhur (Edge Neural, Male)": {
        "engine": "edge",
        "voice": "hi-IN-MadhurNeural",
        "category": "cloud",
    },
    "☁️ Neerja (Edge Expressive, Female)": {
        "engine": "edge",
        "voice": "en-IN-NeerjaExpressiveNeural",
        "category": "cloud",
    },
    "☁️ Prabhat (Edge Neural, Male)": {
        "engine": "edge",
        "voice": "en-IN-PrabhatNeural",
        "category": "cloud",
    },
    "🌐 Divya (Google TTS, Female)": {
        "engine": "gtts",
        "lang": "hi",
        "category": "cloud",
    },

    # ── 🎙️ LOCAL HD VOICES (Offline - Proper Hindi) ──
    "🎙️ Priyamvada (Piper HD, Female)": {
        "engine": "piper",
        "model_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx",
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx.json",
        "model_file": "hi_IN-priyamvada-medium.onnx",
        "category": "local",
    },
    "🎙️ Rohan (Piper HD, Male)": {
        "engine": "piper",
        "model_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx",
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx.json",
        "model_file": "hi_IN-rohan-medium.onnx",
        "category": "local",
    },

    # ── ⚡ FAST LOCAL VOICES (Offline - Kokoro English/Hinglish) ──
    "⚡ Serena (Kokoro English, Female)": {
        "engine": "kokoro",
        "voice": "af_heart",
        "lang": "en-us",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Vivian (Kokoro English, Female)": {
        "engine": "kokoro",
        "voice": "af_bella",
        "lang": "en-us",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Ryan (Kokoro English, Male)": {
        "engine": "kokoro",
        "voice": "am_adam",
        "lang": "en-us",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Aiden (Kokoro English, Male)": {
        "engine": "kokoro",
        "voice": "am_michael",
        "lang": "en-us",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Uncle Fu (Kokoro English, Male)": {
        "engine": "kokoro",
        "voice": "bm_george",
        "lang": "en-us",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Ritz (Kokoro Hindi, Female)": {
        "engine": "kokoro",
        "voice": "hf_alpha",
        "lang": "hi",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Kabir (Kokoro Hindi, Male)": {
        "engine": "kokoro",
        "voice": "hm_omega",
        "lang": "hi",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Meera (Kokoro Hindi 2, Female)": {
        "engine": "kokoro",
        "voice": "hf_beta",
        "lang": "hi",
        "speed": 1.0,
        "category": "local",
    },
    "⚡ Dev (Kokoro Hindi 2, Male)": {
        "engine": "kokoro",
        "voice": "hm_psi",
        "lang": "hi",
        "speed": 1.0,
        "category": "local",
    },

    # ── 💾 LEGACY VOICES ──
    "💾 Rohan Legacy (Sherpa, Male)": {
        "engine": "sherpa",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-hi_IN-rohan-medium.tar.bz2",
        "dir_name": "vits-piper-hi_IN-rohan-medium",
        "model_file": "hi_IN-rohan-medium.onnx",
        "tokens_file": "tokens.txt",
        "category": "local",
    },
    "💾 Priyamvada Legacy (Sherpa, Female)": {
        "engine": "sherpa",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-hi_IN-priyamvada-medium.tar.bz2",
        "dir_name": "vits-piper-hi_IN-priyamvada-medium",
        "model_file": "hi_IN-priyamvada-medium.onnx",
        "tokens_file": "tokens.txt",
        "category": "local",
    },
}

LEGACY_CHARACTER_ALIASES = {
    "Ryan (Qwen3 Local, Male)": "Ryan (Kokoro Local, Male)",
    "Aiden (Qwen3 Local, Male)": "Aiden (Kokoro Local, Male)",
    "Serena (Qwen3 Local, Female)": "Serena (Kokoro Local, Female)",
    "Vivian (Qwen3 Local, Female)": "Vivian (Kokoro Local, Female)",
    "Uncle Fu (Qwen3 Local, Male)": "Uncle Fu (Kokoro Local, Male)",
}

DEFAULT_EDGE_RATE = os.getenv("EDGE_TTS_RATE", "+0%")
DEFAULT_EDGE_PITCH = os.getenv("EDGE_TTS_PITCH", "+0Hz")
STT_PROFILE = os.getenv("STT_PROFILE", "far").strip().lower()
MIC_SAMPLE_RATE = int(os.getenv("MIC_SAMPLE_RATE", "16000"))
MIC_CHUNK_SIZE = int(os.getenv("MIC_CHUNK_SIZE", "1024"))
MIC_CALIBRATION_SECONDS = float(os.getenv("MIC_CALIBRATION_SECONDS", "1.0"))
MIC_CALIBRATION_COOLDOWN = float(os.getenv("MIC_CALIBRATION_COOLDOWN", "20"))
MIC_MIN_RMS = int(os.getenv("MIC_MIN_RMS", "90"))
LISTEN_RETRIES = int(os.getenv("STT_RETRIES", "2"))
LISTEN_BLOCK_AFTER_TTS = float(os.getenv("LISTEN_BLOCK_AFTER_TTS", "1.3"))
LISTEN_BLOCK_MAX_WAIT = float(os.getenv("LISTEN_BLOCK_MAX_WAIT", "6.0"))

_mic_device_raw = os.getenv("MIC_DEVICE_INDEX", "").strip()
MIC_DEVICE_INDEX = int(_mic_device_raw) if _mic_device_raw.isdigit() else None

recognizer = sr.Recognizer() if sr is not None else None
_SPEAK_LOCK = threading.Lock()
_SPEAK_QUEUE = queue.Queue()
_SPEAK_THREAD = None
_LAST_CALIBRATION_TS = 0.0
_TTS_STATE_LOCK = threading.Lock()
_TTS_ACTIVE_COUNT = 0
_LAST_TTS_END_TS = 0.0
_BACKEND_VERSION = 0


def _configure_recognizer_for_profile(profile=STT_PROFILE):
    if recognizer is None:
        return
    mode = str(profile or "far").strip().lower()
    recognizer.dynamic_energy_threshold = True

    if mode == "near":
        recognizer.energy_threshold = 260
        recognizer.pause_threshold = 0.7
        recognizer.non_speaking_duration = 0.3
        recognizer.phrase_threshold = 0.25
        recognizer.dynamic_energy_adjustment_damping = 0.2
        recognizer.dynamic_energy_adjustment_ratio = 1.6
        return

    if mode == "balanced":
        recognizer.energy_threshold = 210
        recognizer.pause_threshold = 0.9
        recognizer.non_speaking_duration = 0.45
        recognizer.phrase_threshold = 0.2
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_adjustment_ratio = 1.5
        return

    # Far profile: more tolerant for distant and softer speech.
    recognizer.energy_threshold = 165
    recognizer.pause_threshold = 1.1
    recognizer.non_speaking_duration = 0.6
    recognizer.phrase_threshold = 0.15
    recognizer.dynamic_energy_adjustment_damping = 0.1
    recognizer.dynamic_energy_adjustment_ratio = 1.35


# ─────────────────────────────────────────────────────────
# ██  AUDIO UTILITIES
# ─────────────────────────────────────────────────────────

def _ensure_mixer_init():
    import pygame
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        except Exception:
            pygame.mixer.init()


def _play_audio_file(file_path):
    """Universal audio playback via pygame mixer."""
    import pygame
    _ensure_mixer_init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)


def _download_file(url, dest_path, progress_callback=None):
    """Download a single file from URL to dest_path."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        return  # Already downloaded

    if progress_callback:
        progress_callback(f"Downloading {os.path.basename(dest_path)}...")

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    total_size = int(response.headers.get("content-length", 0))

    with open(dest_path, "wb") as f:
        downloaded = 0
        for chunk in response.iter_content(8192):
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total_size > 0:
                pct = (downloaded / total_size) * 100
                progress_callback(f"Downloading: {pct:.0f}%")


def _download_and_extract(url, target_dir, progress_callback=None):
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    archive_name = url.split("/")[-1]
    archive_path = os.path.join(target_dir, archive_name)

    if not os.path.exists(archive_path):
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        block_size = 1024 * 8
        if progress_callback:
            progress_callback(f"Downloading {archive_name}...")

        with open(archive_path, "wb") as f, tqdm(
            desc=archive_name, total=total_size, unit="iB", unit_scale=True, unit_divisor=1024
        ) as bar:
            for data in response.iter_content(block_size):
                f.write(data)
                bar.update(len(data))
                if progress_callback:
                    progress_callback(f"Downloading: {bar.n / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB")

    if progress_callback:
        progress_callback(f"Extracting {archive_name}...")

    try:
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(path=target_dir)

        if progress_callback:
            progress_callback("Extraction complete.")

    except Exception as e:
        if progress_callback:
            progress_callback(f"Failed to extract: {e}")
        raise


def _ensure_numba_available_for_qwen():
    """Provide a minimal numba shim when Windows policy blocks numba's native extension.

    qwen-tts imports librosa, and librosa imports numba at module import time.
    On some locked-down Windows setups, numba's `_dispatcher` binary gets blocked
    by Application Control. For Qwen TTS usage here, a no-op decorator shim is
    sufficient to let librosa import and the model run without JIT acceleration.
    """
    if "numba" in sys.modules:
        return

    force_shim = os.getenv("QWEN_TTS_FORCE_NUMBA_SHIM", "0").strip().lower() in {"1", "true", "yes"}
    blocked_policy = False

    if not force_shim:
        try:
            import numba  # noqa: F401
            return
        except Exception as exc:
            message = str(exc).lower()
            blocked_policy = (
                "_dispatcher" in message
                or "application control policy" in message
                or "dll load failed" in message
            )
            if not blocked_policy:
                raise

    import numpy as np

    def _decorator(*args, **kwargs):
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def _wrap(func):
            return func

        return _wrap

    shim = types.ModuleType("numba")
    shim.__dict__.update(
        {
            "__version__": "0-shim",
            "jit": _decorator,
            "njit": _decorator,
            "vectorize": _decorator,
            "guvectorize": _decorator,
            "stencil": _decorator,
            "prange": range,
            "uint32": np.uint32,
            "uint64": np.uint64,
            "int32": np.int32,
            "int64": np.int64,
            "float32": np.float32,
            "float64": np.float64,
            "complex64": np.complex64,
            "complex128": np.complex128,
            "config": types.SimpleNamespace(DISABLE_JIT=True),
        }
    )
    sys.modules["numba"] = shim

    if blocked_policy:
        print("[TTS] Windows policy blocked numba binary; using compatibility shim for Qwen3 TTS.")


def _resolve_local_hf_snapshot(model_name):
    candidate = str(model_name or "").strip()
    if not candidate:
        return candidate

    if os.path.exists(candidate):
        return candidate

    if "/" not in candidate:
        return candidate

    org, repo = candidate.split("/", 1)
    cache_root = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{org}--{repo}"
    refs_main = cache_root / "refs" / "main"
    if not refs_main.exists():
        return candidate

    try:
        snapshot_id = refs_main.read_text(encoding="utf-8").strip()
    except Exception:
        return candidate

    snapshot_dir = cache_root / "snapshots" / snapshot_id
    required_paths = (
        snapshot_dir / "config.json",
        snapshot_dir / "model.safetensors",
    )
    tokenizer_markers = (
        snapshot_dir / "tokenizer.json",
        snapshot_dir / "tokenizer_config.json",
        snapshot_dir / "vocab.json",
        snapshot_dir / "tokenizer.model",
    )

    if snapshot_dir.exists() and all(path.exists() for path in required_paths) and any(
        marker.exists() for marker in tokenizer_markers
    ):
        return str(snapshot_dir)

    return candidate


def _find_first_key(payload, target_key):
    if isinstance(payload, dict):
        value = payload.get(target_key)
        if value not in (None, "", [], {}):
            return value
        for nested in payload.values():
            found = _find_first_key(nested, target_key)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_first_key(item, target_key)
            if found not in (None, "", [], {}):
                return found
    return None


# ─────────────────────────────────────────────────────────
# ██  TTS BACKENDS
# ─────────────────────────────────────────────────────────

class PiperBackend:
    """High-Def local TTS using official piper-tts.
    
    Downloads the model + config from HuggingFace on first use.
    Uses piper-tts for proper phonemization and natural speech.
    """

    def __init__(self, char_info, progress_callback=None):
        try:
            from piper import PiperVoice
        except ImportError as exc:
            print(f"[TTS] PIPER ERROR: Failed to import piper-tts. Details: {exc}")
            raise RuntimeError(
                f"Piper dependencies missing: {exc}. Install: pip install piper-tts"
            ) from exc

        self.models_dir = os.path.join(PROJECT_ROOT, "data", "models", "piper")
        os.makedirs(self.models_dir, exist_ok=True)

        model_file = char_info["model_file"]
        model_path = os.path.join(self.models_dir, model_file)
        config_path = model_path + ".json"

        # Download model + config if needed
        _download_file(char_info["model_url"], model_path, progress_callback)
        _download_file(char_info["config_url"], config_path, progress_callback)

        self.voice = PiperVoice.load(model_path, config_path)
        if progress_callback:
            progress_callback("Piper model loaded successfully.")

    def speak(self, text):
        import wave
        temp_name = f"winter_piper_{uuid.uuid4().hex}.wav"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        try:
            with wave.open(temp_path, "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file, set_wav_format=True)
            _play_audio_file(temp_path)
        except Exception as e:
            print(f"[TTS] Piper local inference failed: {e}")
        finally:
            self._cleanup_file(temp_path)

    def _cleanup_file(self, file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


class SherpaBackend:
    def __init__(self, char_info, progress_callback=None):
        try:
            import sherpa_onnx
            import soundfile as sf
            import pygame as _pygame
        except ImportError as exc:
            raise RuntimeError("Sherpa-ONNX dependencies not available") from exc

        self.sherpa = sherpa_onnx
        self.sf = sf
        self._pygame = _pygame
        _ensure_mixer_init()

        self.char_info = char_info
        self.models_dir = os.path.join(PROJECT_ROOT, "data", "models", "tts")
        self._init_model(progress_callback)

    def _init_model(self, progress_callback):
        os.makedirs(self.models_dir, exist_ok=True)

        espeak_url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2"
        espeak_dir = os.path.join(self.models_dir, "espeak-ng-data")
        if not os.path.exists(espeak_dir):
            _download_and_extract(espeak_url, self.models_dir, progress_callback)

        model_url = self.char_info["url"]
        model_dir_name = self.char_info["dir_name"]
        model_dir = os.path.join(self.models_dir, model_dir_name)

        if not os.path.exists(model_dir):
            _download_and_extract(model_url, self.models_dir, progress_callback)

        self.model_path = os.path.join(model_dir, self.char_info["model_file"])
        self.tokens_path = os.path.join(model_dir, self.char_info["tokens_file"])

        tts_config = self.sherpa.OfflineTtsConfig(
            model=self.sherpa.OfflineTtsModelConfig(
                vits=self.sherpa.OfflineTtsVitsModelConfig(
                    model=str(self.model_path),
                    tokens=str(self.tokens_path),
                    data_dir=str(espeak_dir),
                    length_scale=1.0,
                    noise_scale=0.333,
                    noise_scale_w=0.333,
                ),
            ),
        )
        self.tts = self.sherpa.OfflineTts(tts_config)

    def speak(self, text):
        audio = self.tts.generate(text)
        temp_name = f"winter_tts_{uuid.uuid4().hex}.wav"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)

        self.sf.write(temp_path, audio.samples, audio.sample_rate, subtype='PCM_16')

        try:
            _play_audio_file(temp_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


class EdgeBackend:
    def __init__(self, voice="hi-IN-SwaraNeural", rate=DEFAULT_EDGE_RATE, pitch=DEFAULT_EDGE_PITCH):
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import edge_tts as _edge_tts
            import pygame as _pygame
        except Exception as exc:
            raise RuntimeError("Edge backend dependencies not available") from exc

        self._edge_tts = _edge_tts
        self._pygame = _pygame

        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self._loop = asyncio.new_event_loop()
        _ensure_mixer_init()

    async def _synthesize(self, text, file_path):
        communicator = self._edge_tts.Communicate(text, voice=self.voice, rate=self.rate, pitch=self.pitch)
        await communicator.save(file_path)

    def speak(self, text):
        temp_name = f"winter_tts_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        try:
            self._loop.run_until_complete(self._synthesize(text, temp_path))
            _play_audio_file(temp_path)
        except Exception as e:
            # On 403 or network error, try gTTS as fallback
            error_str = str(e).lower()
            if "403" in error_str or "forbidden" in error_str or "websocket" in error_str:
                print(f"[TTS] Edge 403 blocked, falling back to gTTS: {e}")
                _gtts_fallback_speak(text)
            else:
                raise
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


class GoogleBackend:
    def __init__(self, lang="hi", tld="com"):
        try:
            from gtts import gTTS
            import pygame as _pygame
        except ImportError as exc:
            raise RuntimeError("gTTS dependencies not available") from exc

        self._gtts = gTTS
        self._pygame = _pygame
        _ensure_mixer_init()
        self.lang = lang
        self.tld = tld

    def speak(self, text):
        temp_name = f"winter_tts_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        try:
            tts = self._gtts(text=text, lang=self.lang, tld=self.tld)
            tts.save(temp_path)
            _play_audio_file(temp_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


class KokoroOnnxBackend:
    def __init__(self, char_info, progress_callback=None):
        try:
            import onnxruntime as ort
            import soundfile as sf
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro ONNX dependencies missing. Install: pip install kokoro-onnx"
            ) from exc

        self.ort = ort
        self.sf = sf
        self.Kokoro = Kokoro
        self.voice_name = str(os.getenv("KOKORO_VOICE", "").strip() or char_info.get("voice") or "af_heart")
        self.hindi_voice_name = str(os.getenv("KOKORO_HINDI_VOICE", "hf_alpha").strip() or "hf_alpha")
        self.default_lang = str(char_info.get("lang", "en-us")).strip() or "en-us"
        self.speed = float(os.getenv("KOKORO_SPEED", str(char_info.get("speed", 1.0))).strip() or "1.0")
        self.models_dir = os.path.join(PROJECT_ROOT, "data", "models", "kokoro_onnx")
        self.model_path = ""
        self.voices_path = os.path.join(self.models_dir, "voices-v1.0.bin")
        self.model_url = str(os.getenv("KOKORO_MODEL_URL", "").strip())
        self.voices_url = str(
            os.getenv(
                "KOKORO_VOICES_URL",
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            ).strip()
        )
        self.provider = None
        self.model = None
        self._init_model(progress_callback)

    def _default_model_url(self, prefer_gpu):
        base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
        model_file = "kokoro-v1.0.fp16-gpu.onnx" if prefer_gpu else "kokoro-v1.0.int8.onnx"
        return f"{base}/{model_file}"

    def _cuda_runtime_ready(self):
        if os.name != "nt":
            return True
        try:
            import ctypes
            ctypes.CDLL("cudnn64_9.dll")
            ctypes.CDLL("cublasLt64_12.dll")
            return True
        except Exception:
            return False

    def _resolve_providers(self):
        configured = os.getenv("KOKORO_ONNX_PROVIDER", "auto").strip()
        available = self.ort.get_available_providers()
        if configured and configured.lower() != "auto":
            if configured in available:
                self.provider = configured
                return [configured] if configured == "CPUExecutionProvider" else [configured, "CPUExecutionProvider"]
            self.provider = "CPUExecutionProvider"
            return ["CPUExecutionProvider"]

        if "CUDAExecutionProvider" in available and self._cuda_runtime_ready():
            self.provider = "CUDAExecutionProvider"
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        self.provider = "CPUExecutionProvider"
        return ["CPUExecutionProvider"]

    def _init_model(self, progress_callback=None):
        os.makedirs(self.models_dir, exist_ok=True)
        providers = self._resolve_providers()
        prefer_gpu = providers[0] == "CUDAExecutionProvider"
        effective_model_url = self.model_url or self._default_model_url(prefer_gpu=prefer_gpu)
        self.model_path = os.path.join(self.models_dir, os.path.basename(effective_model_url))
        _download_file(effective_model_url, self.model_path, progress_callback)
        _download_file(self.voices_url, self.voices_path, progress_callback)

        if progress_callback:
            progress_callback(f"Loading Kokoro ONNX on {self.provider}...")

        try:
            session = self.ort.InferenceSession(self.model_path, providers=providers)
        except Exception as first_error:
            # CUDA setup may be present but blocked/missing runtime. Fall back to CPU + int8 model.
            if providers and providers[0] == "CUDAExecutionProvider":
                cpu_model_url = self._default_model_url(prefer_gpu=False)
                self.model_path = os.path.join(self.models_dir, os.path.basename(cpu_model_url))
                _download_file(cpu_model_url, self.model_path, progress_callback)
                self.provider = "CPUExecutionProvider"
                if progress_callback:
                    progress_callback("CUDA unavailable. Falling back to CPU Kokoro model...")
                session = self.ort.InferenceSession(
                    self.model_path,
                    providers=["CPUExecutionProvider"],
                )
            else:
                raise first_error

        active_providers = session.get_providers() or []
        self.provider = active_providers[0] if active_providers else self.provider

        # If CUDA could not be activated, swap to the lighter CPU int8 model for lower latency.
        if self.provider != "CUDAExecutionProvider" and self.model_path.endswith("fp16-gpu.onnx"):
            cpu_model_url = self._default_model_url(prefer_gpu=False)
            self.model_path = os.path.join(self.models_dir, os.path.basename(cpu_model_url))
            _download_file(cpu_model_url, self.model_path, progress_callback)
            session = self.ort.InferenceSession(
                self.model_path,
                providers=["CPUExecutionProvider"],
            )
            active_providers = session.get_providers() or []
            self.provider = active_providers[0] if active_providers else "CPUExecutionProvider"

        self.model = self.Kokoro.from_session(session=session, voices_path=self.voices_path)

        voices = self.model.get_voices()
        if self.voice_name not in voices and voices:
            self.voice_name = voices[0]
            print(f"[TTS] Requested Kokoro voice not found; using '{self.voice_name}'")

        if progress_callback:
            progress_callback(f"Kokoro ONNX ready on {self.provider}.")

    def _detect_language(self, text):
        if _contains_devanagari(text):
            return "hi"
        return self.default_lang

    def speak(self, text):
        lang = self._detect_language(text)
        voice_to_use = self.voice_name
        if lang == "hi" and not voice_to_use.startswith("h"):
            voice_to_use = self.hindi_voice_name
            
        if voice_to_use not in self.model.get_voices():
            voice_to_use = self.voice_name
            
        audio_array, sample_rate = self.model.create(
            text=text,
            voice=voice_to_use,
            speed=self.speed,
            lang=lang,
        )
        temp_name = f"winter_kokoro_{uuid.uuid4().hex}.wav"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        try:
            self.sf.write(temp_path, audio_array, sample_rate)
            _play_audio_file(temp_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


def _gtts_fallback_speak(text):
    """Emergency fallback when Edge TTS gets 403 blocked."""
    try:
        from gtts import gTTS
        temp_name = f"winter_fallback_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        tts = gTTS(text=text, lang="hi")
        tts.save(temp_path)
        _play_audio_file(temp_path)
        try:
            os.remove(temp_path)
        except Exception:
            pass
    except Exception:
        pass  # Silently fail if even gTTS doesn't work


# ─────────────────────────────────────────────────────────
# ██  TTS MANAGER (Engine Selector)
# ─────────────────────────────────────────────────────────

class TTSManager:
    def __init__(self):
        raw_char = os.getenv("TTS_CHARACTER", "Ryan (Kokoro Local, Male)")
        self.active_character = raw_char.strip().strip('"').strip("'")
        self.active_character = LEGACY_CHARACTER_ALIASES.get(self.active_character, self.active_character)

        if self.active_character not in VOICE_CHARACTERS:
            # Smart fuzzy match: try exact substring first, then name-based
            query = self.active_character.lower().strip()
            first_name = query.split("(")[0].strip().split()[0] if query else ""
            
            best_match = None
            # Pass 1: exact substring match
            for key in VOICE_CHARACTERS.keys():
                if query in key.lower() or key.lower() in query:
                    best_match = key
                    break
            
            # Pass 2: match by first name (e.g., "Rohan" matches "Rohan (Local HD, Male)")
            if best_match is None and first_name:
                for key in VOICE_CHARACTERS.keys():
                    if key.lower().startswith(first_name):
                        best_match = key
                        break
            
            self.active_character = best_match or "Ryan (Kokoro Local, Male)"

        self.backend = None
        self._init_backend()

    def _init_backend(self, progress_callback=None):
        char_info = VOICE_CHARACTERS[self.active_character]
        engine = char_info.get("engine", "edge")

        print(f"[TTS] Initializing backend: {self.active_character} (engine={engine})")

        try:
            if engine == "piper":
                self.backend = PiperBackend(char_info, progress_callback)
            elif engine == "sherpa":
                self.backend = SherpaBackend(char_info, progress_callback)
            elif engine == "kokoro":
                self.backend = KokoroOnnxBackend(char_info, progress_callback)
            elif engine == "gtts":
                self.backend = GoogleBackend(lang=char_info.get("lang", "hi"))
            else:
                self.backend = EdgeBackend(voice=char_info.get("voice", "hi-IN-SwaraNeural"))
        except Exception as e:
            import traceback
            print(f"[TTS] CRITICAL: Failed to init {engine} backend for '{self.active_character}'")
            print(f"[TTS] Error Detail: {str(e)}")
            print(f"[TTS] Falling back to Piper HD for stability.")
            try:
                fallback_char = VOICE_CHARACTERS.get("Rohan (Local HD, Male)")
                self.backend = PiperBackend(fallback_char, progress_callback)
            except Exception as e2:
                print(f"[TTS] Global fallback failed: {e2}")
                self.backend = None

    def speak(self, text):
        if self.backend:
            self.backend.speak(text)


def _build_backend():
    return TTSManager()


# ─────────────────────────────────────────────────────────
# ██  TEXT NORMALIZATION
# ─────────────────────────────────────────────────────────

def _normalize_transcript(text):
    normalized = str(text).strip().lower()
    phrase_replacements = {
        "a winter": "hey winter",
        "pay winter": "hey winter",
        "hey venter": "hey winter",
        "stop listen": "stop listening",
        "go to slip": "go to sleep",
    }

    for wrong, corrected in phrase_replacements.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", corrected, normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def _cleanup_text_for_tts(text):
    cleaned = unicodedata.normalize("NFKC", str(text))
    cleaned = (
        cleaned.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2014", ", ")
        .replace("\u2013", ", ")
        .replace("\u2026", "...")
    )
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _contains_devanagari(text):
    return bool(re.search(r"[\u0900-\u097F]", str(text)))


def _romanize_devanagari(text):
    vowels = {
        "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u",
        "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri",
    }
    matras = {
        "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
        "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
    }
    consonants = {
        "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "च": "ch", "छ": "chh",
        "ज": "j", "झ": "jh", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
        "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
        "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
        "य": "y", "र": "r", "ल": "l", "व": "v",
        "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    }
    signs = {"ं": "n", "ँ": "n", "ः": "h", "ऽ": "", "।": "."}
    virama = "्"

    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in vowels:
            result.append(vowels[ch])
            i += 1
            continue
        if ch in consonants:
            base = consonants[ch]
            next_ch = text[i + 1] if i + 1 < len(text) else ""
            if next_ch in matras:
                result.append(base + matras[next_ch])
                i += 2
                continue
            if next_ch == virama:
                result.append(base)
                i += 2
                continue
            result.append(base + "a")
            i += 1
            continue
        if ch in matras:
            result.append(matras[ch])
        elif ch in signs:
            result.append(signs[ch])
        else:
            result.append(ch)
        i += 1

    spoken = "".join(result)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken


def _normalize_for_tts(text, preserve_devanagari=False):
    spoken = _cleanup_text_for_tts(text)
    word_replacements = {
        r"\bnhi\b": "nahi",
        r"\bni\b": "nahi",
        r"\bkr\b": "kar",
        r"\bkro\b": "karo",
        r"\bpls\b": "please",
        r"\bpm\b": "prime minister",
    }

    for pattern, replacement in word_replacements.items():
        spoken = re.sub(pattern, replacement, spoken, flags=re.IGNORECASE)

    if _contains_devanagari(spoken) and not preserve_devanagari:
        spoken = _romanize_devanagari(spoken)

    return spoken


def _chunk_text(text, max_len=180):
    sentence_chunks = re.split(r"(?<=[.!?])\s+", str(text))
    chunks = []
    current = ""

    for part in sentence_chunks:
        part = part.strip()
        if not part:
            continue

        if len(current) + len(part) + 1 <= max_len:
            current = f"{current} {part}".strip()
        else:
            if current:
                chunks.append(current)
            current = part

    if current:
        chunks.append(current)

    return chunks if chunks else [str(text)]


# ─────────────────────────────────────────────────────────
# ██  SPEECH RECOGNITION
# ─────────────────────────────────────────────────────────

def _recognize_with_fallback(audio):
    if recognizer is None or sr is None:
        return f"Error: Speech recognition dependency unavailable ({_SR_IMPORT_ERROR or 'missing module'})"
    request_error = None

    for language in LANGUAGE_PREFERENCES:
        try:
            transcript = recognizer.recognize_google(audio, language=language)
            if transcript and transcript.strip():
                return _normalize_transcript(transcript)
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            request_error = str(e)
            break

    if request_error:
        return f"Error: {request_error}"

    return "Could not understand"


def _get_microphone():
    if sr is None:
        raise RuntimeError(f"Speech recognition dependency unavailable ({_SR_IMPORT_ERROR or 'missing module'})")
    kwargs = {
        "sample_rate": MIC_SAMPLE_RATE,
        "chunk_size": MIC_CHUNK_SIZE,
    }
    if MIC_DEVICE_INDEX is not None:
        kwargs["device_index"] = MIC_DEVICE_INDEX
    return sr.Microphone(**kwargs)


def _audio_rms(audio):
    try:
        frame_data = getattr(audio, "frame_data", b"") or b""
        sample_width = int(getattr(audio, "sample_width", 0) or 0)
        if not frame_data or sample_width <= 0:
            return 0

        sample_count = len(frame_data) // sample_width
        if sample_count <= 0:
            return 0

        total = 0.0
        for index in range(sample_count):
            start = index * sample_width
            chunk = frame_data[start : start + sample_width]
            if len(chunk) < sample_width:
                continue

            if sample_width == 1:
                value = chunk[0] - 128
            else:
                value = int.from_bytes(chunk, byteorder="little", signed=True)
            total += float(value * value)

        if total <= 0:
            return 0
        return int(math.sqrt(total / sample_count))
    except Exception:
        return 0


def _capture_audio(timeout, phrase_time_limit):
    global _LAST_CALIBRATION_TS
    with _get_microphone() as source:
        now = time.time()
        if now - _LAST_CALIBRATION_TS >= MIC_CALIBRATION_COOLDOWN:
            recognizer.adjust_for_ambient_noise(source, duration=MIC_CALIBRATION_SECONDS)
            _LAST_CALIBRATION_TS = now

        return recognizer.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )


# ─────────────────────────────────────────────────────────
# ██  TTS STATE MANAGEMENT
# ─────────────────────────────────────────────────────────

def _mark_tts_started():
    global _TTS_ACTIVE_COUNT
    with _TTS_STATE_LOCK:
        _TTS_ACTIVE_COUNT += 1


def _mark_tts_finished():
    global _TTS_ACTIVE_COUNT, _LAST_TTS_END_TS
    with _TTS_STATE_LOCK:
        _TTS_ACTIVE_COUNT = max(0, _TTS_ACTIVE_COUNT - 1)
        _LAST_TTS_END_TS = time.time()


def _is_tts_blocking_listen():
    with _TTS_STATE_LOCK:
        if _TTS_ACTIVE_COUNT > 0:
            return True
        return (time.time() - _LAST_TTS_END_TS) < LISTEN_BLOCK_AFTER_TTS


def _wait_for_tts_clear(max_wait=LISTEN_BLOCK_MAX_WAIT):
    deadline = time.time() + max(0.0, float(max_wait))
    while _is_tts_blocking_listen():
        if time.time() >= deadline:
            return False
        time.sleep(0.05)
    return True


# ─────────────────────────────────────────────────────────
# ██  BACKGROUND TTS WORKER
# ─────────────────────────────────────────────────────────

def _speak_worker():
    backend = None
    backend_version = -1

    while True:
        item = _SPEAK_QUEUE.get()
        if item is None:
            _SPEAK_QUEUE.task_done()
            break

        chunks, done_event = item
        try:
            if backend is None or backend_version != _BACKEND_VERSION:
                backend = _build_backend()
                backend_version = _BACKEND_VERSION

            _mark_tts_started()
            for chunk in chunks:
                try:
                    backend.speak(chunk)
                except Exception:
                    backend = _build_backend()
                    backend_version = _BACKEND_VERSION
                    try:
                        backend.speak(chunk)
                    except Exception:
                        pass  # Skip chunk on double failure
        except Exception:
            pass
        finally:
            _mark_tts_finished()
            done_event.set()
            _SPEAK_QUEUE.task_done()


def _ensure_speak_worker():
    global _SPEAK_THREAD
    with _SPEAK_LOCK:
        if _SPEAK_THREAD is not None and _SPEAK_THREAD.is_alive():
            return

        _SPEAK_THREAD = threading.Thread(target=_speak_worker, daemon=True, name="tts-worker")
        _SPEAK_THREAD.start()


# ─────────────────────────────────────────────────────────
# ██  PUBLIC API
# ─────────────────────────────────────────────────────────

def speak(text):
    active_character = os.getenv("TTS_CHARACTER", "")
    is_kokoro = "kokoro" in active_character.lower()
    output = _normalize_for_tts(text, preserve_devanagari=is_kokoro)
    if not output:
        return

    max_len = 110 if is_kokoro else 180
    chunks = _chunk_text(output, max_len=max_len)

    try:
        _ensure_speak_worker()
        done_event = threading.Event()
        _SPEAK_QUEUE.put((chunks, done_event))

        timeout = max(8.0, min(45.0, (len(output) / 9.0) + 6.0))
        if done_event.wait(timeout=timeout):
            return
    except Exception:
        return


def reset_tts_backend():
    """Bump backend version so the worker thread rebuilds with the new voice.
    
    NOTE: Do NOT call load_dotenv here! The UI (_write_env_values) already
    sets os.environ directly. Calling load_dotenv(override=True) here would
    overwrite the freshly-set value with the (possibly stale) .env file.
    """
    global _BACKEND_VERSION
    with _SPEAK_LOCK:
        _BACKEND_VERSION += 1
    print(f"[TTS] Backend version bumped to {_BACKEND_VERSION}. Active char: {os.getenv('TTS_CHARACTER', 'NOT SET')}")


def preview_tts(text, character=None):
    """Play a sample using the specified character or the default in ENV."""
    if character:
        os.environ["TTS_CHARACTER"] = character

    selected_character = os.getenv("TTS_CHARACTER", "Ryan (Kokoro Local, Male)").strip().strip('"').strip("'")
    selected_character = LEGACY_CHARACTER_ALIASES.get(selected_character, selected_character)
    char_info = VOICE_CHARACTERS.get(selected_character)

    if char_info and char_info.get("engine") == "kokoro":
        backend = KokoroOnnxBackend(char_info)
        backend.speak(_normalize_for_tts(text, preserve_devanagari=True))
        return

    backend = TTSManager()
    backend.speak(_normalize_for_tts(text))


def listen(timeout=6, phrase_time_limit=8):
    if recognizer is None or sr is None:
        return f"Error: Speech recognition dependency unavailable ({_SR_IMPORT_ERROR or 'missing module'})"

    _wait_for_tts_clear()

    retries = max(1, LISTEN_RETRIES)
    best_result = None

    for attempt in range(retries):
        effective_timeout = timeout + (attempt * 2)
        effective_phrase_limit = phrase_time_limit + (attempt * 3)

        _wait_for_tts_clear()

        try:
            audio = _capture_audio(effective_timeout, effective_phrase_limit)
        except sr.WaitTimeoutError:
            continue
        except Exception as e:
            return f"Error: {str(e)}"

        rms = _audio_rms(audio)
        if rms < MIC_MIN_RMS and attempt < retries - 1:
            continue

        try:
            result = _recognize_with_fallback(audio)
        except Exception as e:
            return f"Error: {str(e)}"

        if result and not result.startswith("Error:") and result != "Could not understand":
            return result

        best_result = result

    return best_result


# ─────────────────────────────────────────────────────────
# ██  MODULE INIT
# ─────────────────────────────────────────────────────────

_ensure_speak_worker()
_configure_recognizer_for_profile()
