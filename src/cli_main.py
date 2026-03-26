import threading

from modules.command_handler import handle_command
from modules.automation import organize_downloads
from utils.background import background_worker
from utils.suggestions import get_action_suggestions
from utils.voice import listen, speak
from utils.wake_word import get_wake_acknowledgement, listen_for_wake_word


def _should_exit(text):
    lowered = str(text).lower()
    return any(phrase in lowered for phrase in ("exit", "quit", "band kar", "shut down"))


def _should_sleep(text):
    lowered = str(text).lower()
    return any(
        phrase in lowered
        for phrase in (
            "sleep",
            "go to sleep",
            "stop listening",
            "stop listen",
            "sleep mode",
            "so ja",
            "pause",
        )
    )


def _is_noise_text(text):
    lowered = str(text).strip().lower()
    return lowered in {"could not understand", ""} or lowered.startswith("error:")


def main():
    print("Winter AI Started (Say 'Hey Winter' to activate)\n")
    thread = threading.Thread(target=background_worker, daemon=True)
    thread.start()

    while True:
        listen_for_wake_word()
        wake_reply = get_wake_acknowledgement()
        print("AI:", wake_reply)
        speak(wake_reply)

        while True:
            user_input = listen()
            if not user_input or _is_noise_text(user_input):
                continue

            if _should_exit(user_input):
                print("Shutting down...")
                return

            if _should_sleep(user_input):
                print("Sleep mode on.")
                break

            if "winter" in user_input.lower():
                continue

            response = handle_command(user_input)
            print("AI:", response)
            speak(response)

            actions = get_action_suggestions()

            for action in actions:
                print(f"\n{action['message']}")
                speak(action["message"])
                choice = input("Type 'yes' to proceed or 'no' to skip: ").lower().strip()

                if choice == "yes":
                    if action["type"] == "organize_downloads":
                        result = organize_downloads()
                        print("AI:", result)
                        speak(result)
                    elif action["type"] == "repeat_warning":
                        result = "Try creating a custom command for this task."
                        print("AI:", result)
                        speak(result)
                else:
                    skip_message = "Action skipped."
                    print("AI:", skip_message)
                    speak(skip_message)


if __name__ == "__main__":
    main()
