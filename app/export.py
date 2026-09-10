"""Markdown rendering used by the conversation export endpoint."""
import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Turn a conversation title into a filesystem-safe slug for a download filename."""
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug or "conversation"


def render_markdown(conversation: dict, messages: list[dict]) -> str:
    """Render a conversation transcript as plain markdown.

    Layout: an H1 title, then one H2 per turn ("User" / "Assistant") followed
    by that turn's raw message content.
    """
    lines = [f"# {conversation['title']}", ""]
    for message in messages:
        heading = "## User" if message["role"] == "user" else "## Assistant"
        lines.append(heading)
        lines.append("")
        lines.append(message["content"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
