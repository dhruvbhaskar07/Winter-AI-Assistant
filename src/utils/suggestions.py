from utils.memory import load_memory

def get_action_suggestions():
    memory = load_memory()
    history = memory.get("history", [])
    actions = []

    if len(history) >= 3:
        last_commands = [str(item.get("user", "")).strip().lower() for item in history[-3:]]
        if last_commands and len(set(last_commands)) == 1:
            actions.append(
                {
                    "type": "repeat_warning",
                    "message": "You are repeating the same command. Do you want to automate it?",
                }
            )

    return actions
