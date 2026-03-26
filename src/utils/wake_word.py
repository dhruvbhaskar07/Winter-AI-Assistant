import os
import random

from services.llm_service import generate_wake_acknowledgement
from utils.voice import listen

WAKE_WORD = "hey winter"
WAKE_ACK_RESPONSES = [
    "Yes boss.",
    "Yes sirji.",
    "Haan ji, boliye.",
    "Yahi hoon sir.",
    "Ji boss, ready hoon.",
    "Hukum mere aaka.",
    "Ready when you are.",
]


def _is_wake_text(text):
    lowered = str(text).strip().lower()
    if not lowered:
        return False

    if WAKE_WORD in lowered:
        return True

    # Common speech-to-text variants: "a winter", "hi winter", "winter"
    wake_variants = ("hi winter", "hey winter", "a winter", "winter")
    return any(variant in lowered for variant in wake_variants)


def listen_for_wake_word():
    while True:
        text = listen()

        if _is_wake_text(text):
            return True


def get_wake_acknowledgement():
    mode = os.getenv("WAKE_ACK_MODE", "auto").strip().lower()

    if mode in {"llm", "auto"}:
        llm_line = generate_wake_acknowledgement()
        if llm_line:
            return llm_line

    return random.choice(WAKE_ACK_RESPONSES)
