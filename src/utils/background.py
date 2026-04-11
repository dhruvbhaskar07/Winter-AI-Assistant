import time

from modules.automation import create_folder, organize_downloads, rename_file
from utils.decision_engine import evaluate_actions
from utils.safety import confirm_action


def _execute_action(action_name, payload):
    if action_name == "organize_downloads":
        return organize_downloads()

    if action_name == "create_folder":
        folder_name = str(payload.get("folder_name", "New Folder")).strip()
        base_path = str(payload.get("base_path", ".")).strip() or "."
        return create_folder(folder_name, base_path=base_path)

    if action_name == "rename_file":
        old_name = str(payload.get("old_name", "")).strip()
        new_name = str(payload.get("new_name", "")).strip()
        if not old_name or not new_name:
            return "Rename skipped: missing old_name/new_name"
        return rename_file(old_name, new_name)

    return None


def background_worker():
    while True:
        decisions = evaluate_actions()

        for decision in decisions:
            action_name = decision["action"]
            payload = decision.get("payload", {})
            message = decision.get("message", f"Execute '{action_name}'")

            if decision.get("auto"):
                result = _execute_action(action_name, payload)
                if result is None:
                    continue
                else:
                    result_message = f"AI: {result}"
                    print(result_message)
                continue

            # Strict consent mode: never execute anything without explicit user confirmation.
            if not confirm_action(
                f"Decision available: {message} (action={action_name}, confidence={decision['confidence']:.2f}). Proceed?"
            ):
                continue

            result = _execute_action(action_name, payload)
            if result is None:
                continue
            else:
                result_message = f"AI: {result}"
                print(result_message)

        time.sleep(20)
