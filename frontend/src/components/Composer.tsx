import { useState } from "react";
import type { KeyboardEvent } from "react";
import { useApp } from "../state/store";

export function Composer() {
  const { state, actions } = useApp();
  const [text, setText] = useState("");
  const disabled = state.pending || state.selectedId == null;

  const send = () => {
    if (disabled || !text.trim()) return;
    void actions.send(text);
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div className="composer">
      <textarea
        className="composer-input"
        data-testid="composer-input"
        placeholder="Send a message…"
        value={text}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
      />
      <button
        className="composer-send"
        data-testid="composer-send"
        disabled={disabled}
        onClick={send}
      >
        Send
      </button>
    </div>
  );
}
