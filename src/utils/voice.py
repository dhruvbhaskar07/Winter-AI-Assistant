import asyncio
import audioop
import os
import queue
import re
import tempfile
import threading
import time
import unicodedata
import uuid

import speech_recognition as sr


LANGUAGE_PREFERENCES = ("en-IN", "hi-IN", "en-US")
DEFAULT_EDGE_VOICE = os.getenv("EDGE_TTS_VOICE", "en-IN-NeerjaNeural")
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

recognizer = sr.Recognizer()
_SPEAK_LOCK = threading.Lock()
_SPEAK_QUEUE = queue.Queue()
_SPEAK_THREAD = None
_LAST_CALIBRATION_TS = 0.0
_TTS_STATE_LOCK = threading.Lock()
_TTS_ACTIVE_COUNT = 0
_LAST_TTS_END_TS = 0.0


def _configure_recognizer_for_profile(profile=STT_PROFILE):
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


class EdgeBackend:
    def __init__(self, voice=DEFAULT_EDGE_VOICE, rate=DEFAULT_EDGE_RATE, pitch=DEFAULT_EDGE_PITCH):
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
        self._init_player()

    def _init_player(self):
        self._pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)

    async def _synthesize(self, text, file_path):
        communicator = self._edge_tts.Communicate(text, voice=self.voice, rate=self.rate, pitch=self.pitch)
        await communicator.save(file_path)

    def _play_file(self, file_path):
        self._pygame.mixer.music.load(file_path)
        self._pygame.mixer.music.play()
        while self._pygame.mixer.music.get_busy():
            time.sleep(0.05)

    def speak(self, text):
        temp_name = f"winter_tts_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)
        try:
            self._loop.run_until_complete(self._synthesize(text, temp_path))
            self._play_file(temp_path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass


def _build_backend():
    return EdgeBackend()


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
    # Simple practical transliteration for clearer English-voice TTS.
    vowels = {
        "अ": "a",
        "आ": "aa",
        "इ": "i",
        "ई": "ee",
        "उ": "u",
        "ऊ": "oo",
        "ए": "e",
        "ऐ": "ai",
        "ओ": "o",
        "औ": "au",
        "ऋ": "ri",
    }
    matras = {
        "ा": "aa",
        "ि": "i",
        "ी": "ee",
        "ु": "u",
        "ू": "oo",
        "े": "e",
        "ै": "ai",
        "ो": "o",
        "ौ": "au",
        "ृ": "ri",
    }
    consonants = {
        "क": "k",
        "ख": "kh",
        "ग": "g",
        "घ": "gh",
        "च": "ch",
        "छ": "chh",
        "ज": "j",
        "झ": "jh",
        "ट": "t",
        "ठ": "th",
        "ड": "d",
        "ढ": "dh",
        "त": "t",
        "थ": "th",
        "द": "d",
        "ध": "dh",
        "न": "n",
        "प": "p",
        "फ": "ph",
        "ब": "b",
        "भ": "bh",
        "म": "m",
        "य": "y",
        "र": "r",
        "ल": "l",
        "व": "v",
        "श": "sh",
        "ष": "sh",
        "स": "s",
        "ह": "h",
        "ळ": "l",
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


def _normalize_for_tts(text):
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

    if _contains_devanagari(spoken):
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


def _recognize_with_fallback(audio):
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
    kwargs = {
        "sample_rate": MIC_SAMPLE_RATE,
        "chunk_size": MIC_CHUNK_SIZE,
    }
    if MIC_DEVICE_INDEX is not None:
        kwargs["device_index"] = MIC_DEVICE_INDEX
    return sr.Microphone(**kwargs)


def _audio_rms(audio):
    try:
        return audioop.rms(audio.frame_data, audio.sample_width)
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


def _speak_worker():
    backend = None

    while True:
        item = _SPEAK_QUEUE.get()
        if item is None:
            _SPEAK_QUEUE.task_done()
            break

        chunks, done_event = item
        try:
            if backend is None:
                backend = _build_backend()

            _mark_tts_started()
            for chunk in chunks:
                try:
                    backend.speak(chunk)
                except Exception:
                    backend = _build_backend()
                    backend.speak(chunk)
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


def speak(text):
    output = _normalize_for_tts(text)
    if not output:
        return

    chunks = _chunk_text(output)

    try:
        _ensure_speak_worker()
        done_event = threading.Event()
        _SPEAK_QUEUE.put((chunks, done_event))

        timeout = max(8.0, min(45.0, (len(output) / 9.0) + 6.0))
        if done_event.wait(timeout=timeout):
            return
    except Exception:
        return


def listen(timeout=6, phrase_time_limit=8):
    _wait_for_tts_clear()

    retries = max(1, LISTEN_RETRIES)
    best_result = None

    for attempt in range(retries):
        effective_timeout = timeout + (attempt * 2)
        effective_phrase_limit = phrase_time_limit + (attempt * 3)

        # Prevent Winter's own just-finished speech from being captured as user input.
        _wait_for_tts_clear()

        try:
            audio = _capture_audio(effective_timeout, effective_phrase_limit)
        except sr.WaitTimeoutError:
            continue
        except Exception as e:
            return f"Error: {str(e)}"

        rms = _audio_rms(audio)
        if rms < MIC_MIN_RMS and attempt < retries - 1:
            # Too soft/noisy frame: retry once with a longer capture window.
            continue

        try:
            result = _recognize_with_fallback(audio)
        except Exception as e:
            return f"Error: {str(e)}"

        if result and not result.startswith("Error:") and result != "Could not understand":
            return result

        best_result = result

    return best_result


_ensure_speak_worker()
_configure_recognizer_for_profile()
