"""Prompt templates and conversation-history flattening."""

SYSTEM_PREAMBLE = (
    "You are a concise, helpful assistant. Answer directly and keep "
    "responses focused on the question asked."
)


def flatten_history(messages: list[dict], new_message: str) -> str:
    lines = [SYSTEM_PREAMBLE, ""]
    for message in messages:
        speaker = "User" if message["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {message['content']}")
    lines.append(f"User: {new_message}")
    lines.append("Assistant:")
    return "\n".join(lines)


def token_estimate(text: str) -> int:
    """Rough token count: ~0.75 words per token. An estimate, not a tokenizer."""
    return max(1, round(len(text.split()) / 0.75))
