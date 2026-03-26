from utils.suggestions import get_action_suggestions


AUTO_THRESHOLD = 0.7
HIGH_RISK_KEYWORDS = ("delete", "remove", "rename", "move", "format", "reset")
LOW_RISK_HINTS = ("organize", "cleanup", "suggest", "repeat")


def _estimate_confidence(action):
    action_type = str(action.get("type", "")).lower()
    message = str(action.get("message", "")).lower()
    blob = f"{action_type} {message}"

    # Suggestions can override confidence directly
    if isinstance(action.get("confidence"), (int, float)):
        return max(0.0, min(1.0, float(action["confidence"])))

    confidence = 0.5

    if any(hint in blob for hint in LOW_RISK_HINTS):
        confidence += 0.2
    if any(keyword in blob for keyword in HIGH_RISK_KEYWORDS):
        confidence -= 0.25

    if action_type.startswith("organize_"):
        confidence += 0.15
    elif action_type.startswith("repeat_"):
        confidence -= 0.1

    return max(0.0, min(1.0, confidence))


def _should_auto_execute(action, confidence):
    # Suggestions can override auto decision directly
    if isinstance(action.get("auto"), bool):
        return action["auto"]

    action_type = str(action.get("type", "")).lower()
    message = str(action.get("message", "")).lower()
    blob = f"{action_type} {message}"

    high_risk = any(keyword in blob for keyword in HIGH_RISK_KEYWORDS)
    return confidence >= AUTO_THRESHOLD and not high_risk


def evaluate_actions():
    actions = get_action_suggestions()
    decisions = []

    for action in actions:
        action_type = str(action.get("type", "")).strip()
        if not action_type:
            continue

        confidence = _estimate_confidence(action)
        auto = _should_auto_execute(action, confidence)
        decisions.append(
            {
                "action": action_type,
                "confidence": confidence,
                "auto": auto,
                "message": action.get("message", "Action available"),
                "payload": action,
            }
        )

    return decisions
