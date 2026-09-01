from app.prompting import SYSTEM_PREAMBLE, flatten_history, token_estimate


def test_flatten_empty_history():
    prompt = flatten_history([], "Hello there")
    assert prompt.startswith(SYSTEM_PREAMBLE)
    assert prompt.endswith("User: Hello there\nAssistant:")


def test_flatten_orders_turns():
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    prompt = flatten_history(history, "second question")
    a = prompt.index("User: first question")
    b = prompt.index("Assistant: first answer")
    c = prompt.index("User: second question")
    assert a < b < c
    assert prompt.endswith("Assistant:")


def test_flatten_is_deterministic():
    history = [{"role": "user", "content": "x"}]
    assert flatten_history(history, "y") == flatten_history(history, "y")


def test_token_estimate():
    assert token_estimate("") == 1
    assert token_estimate("one two three four five six") == 8  # 6 words / 0.75
