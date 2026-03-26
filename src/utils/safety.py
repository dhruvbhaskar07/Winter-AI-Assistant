_CONFIRM_HANDLER = None


def _safe_speak(text):
    try:
        from utils.voice import speak

        speak(text)
    except Exception:
        pass


def set_confirm_handler(handler):
    global _CONFIRM_HANDLER
    _CONFIRM_HANDLER = handler


def clear_confirm_handler():
    global _CONFIRM_HANDLER
    _CONFIRM_HANDLER = None


def confirm_action(message, use_voice=False):
    prompt = f"WARNING: {message}"
    if _CONFIRM_HANDLER is not None:
        try:
            confirmed = bool(_CONFIRM_HANDLER(prompt))
            if use_voice:
                _safe_speak("Confirmed." if confirmed else "Cancelled.")
            return confirmed
        except Exception:
            pass

    print(f"\n{prompt}")
    if use_voice:
        _safe_speak(prompt)
        _safe_speak("Type yes to confirm or no to cancel.")

    choice = input("Type 'yes' to confirm or 'no' to cancel: ").strip().lower()
    confirmed = choice == "yes"

    if use_voice:
        _safe_speak("Confirmed." if confirmed else "Cancelled.")

    return confirmed
