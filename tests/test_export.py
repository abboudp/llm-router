from app.export import render_markdown, slugify


def test_slugify_lowercases_and_hyphenates_spaces():
    assert slugify("My First Chat") == "my-first-chat"


def test_slugify_strips_punctuation():
    assert slugify("What's up? / testing!!") == "what-s-up-testing"


def test_slugify_collapses_repeated_separators():
    assert slugify("a   b---c") == "a-b-c"


def test_slugify_empty_or_symbols_only_falls_back():
    assert slugify("") == "conversation"
    assert slugify("!!!") == "conversation"


def test_slugify_drops_non_ascii_letters_but_never_raises():
    # Accented/non-ASCII characters aren't in [a-z0-9], so they become
    # separators like any other punctuation — the result stays a plain,
    # filesystem-safe ASCII slug no matter what the title contains.
    assert slugify("café résumé") == "caf-r-sum"
    assert slugify("日本語のタイトル") == "conversation"


def test_render_markdown_includes_title_as_h1():
    body = render_markdown({"title": "My chat"}, [])
    assert body.startswith("# My chat\n")


def test_render_markdown_orders_turns_with_role_headings():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    body = render_markdown({"title": "T"}, messages)
    assert "## User" in body
    assert "## Assistant" in body
    assert body.index("## User") < body.index("## Assistant")
    assert "hello" in body
    assert "hi there" in body


def test_render_markdown_empty_conversation_has_only_title():
    body = render_markdown({"title": "Empty"}, [])
    assert body == "# Empty\n"
