import random


def strip_action(text: str) -> str:
    if "(" not in text or ")" not in text:
        return text.strip()
    parts = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            continue
        if depth == 0:
            parts.append(ch)
    return "".join(parts).strip()


def pick_action(actions: list[str], fallback: str) -> str:
    if actions:
        candidates = [item for item in actions if item.strip()]
        return random.choice(candidates or actions)
    return fallback


def attach_action(reply: str, action: str) -> str:
    if not action:
        return reply
    return f"{reply}({action})"
