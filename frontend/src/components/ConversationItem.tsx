import { useEffect, useRef, useState } from "react";
import type { Conversation } from "../api/types";
import { relativeTime } from "../lib/time";
import { useApp } from "../state/store";

export function ConversationItem({ conversation }: { conversation: Conversation }) {
  const { state, actions } = useApp();
  const selected = state.selectedId === conversation.id;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLSpanElement>(null);

  // Closes the menu on an outside click or Esc — the two standard ways a
  // dropdown is expected to dismiss itself without picking an item.
  useEffect(() => {
    if (!menuOpen) return;
    const handleOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  const rename = (event: React.MouseEvent) => {
    event.stopPropagation();
    setMenuOpen(false);
    const title = window.prompt("Rename conversation", conversation.title);
    if (title && title.trim() && title !== conversation.title) {
      void actions.rename(conversation.id, title.trim());
    }
  };

  const remove = (event: React.MouseEvent) => {
    event.stopPropagation();
    setMenuOpen(false);
    void actions.remove(conversation.id);
  };

  const togglePin = (event: React.MouseEvent) => {
    event.stopPropagation();
    setMenuOpen(false);
    void actions.setPinned(conversation.id, !conversation.pinned);
  };

  const exportConversation = (event: React.MouseEvent) => {
    event.stopPropagation();
    setMenuOpen(false);
    const link = document.createElement("a");
    link.href = `/v1/conversations/${conversation.id}/export`;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <div
      className={`conversation-item${selected ? " selected" : ""}${
        conversation.pinned ? " pinned" : ""
      }`}
      data-testid="conversation-item"
      onClick={() => void actions.select(conversation.id)}
    >
      <span className="conversation-main">
        <span className="conversation-title" data-testid="conversation-title">
          {conversation.title}
        </span>
        <span className="conversation-time">{relativeTime(conversation.updated_at)}</span>
      </span>
      <span className="conversation-menu-anchor" ref={menuRef}>
        <button
          className="conversation-menu-trigger"
          data-testid="conversation-menu"
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
          aria-label="Conversation actions"
          aria-haspopup="true"
          aria-expanded={menuOpen}
        >
          …
        </button>
        {menuOpen && (
          <div className="conversation-menu" role="menu">
            <button
              className={`conversation-menu-item${conversation.pinned ? " active" : ""}`}
              data-testid="pin-conversation"
              onClick={togglePin}
              role="menuitemcheckbox"
              aria-checked={conversation.pinned}
            >
              {conversation.pinned ? "Unpin" : "Pin"}
            </button>
            <button
              className="conversation-menu-item"
              data-testid="rename-conversation"
              onClick={rename}
              role="menuitem"
            >
              Rename
            </button>
            <button
              className="conversation-menu-item"
              data-testid="export-conversation"
              onClick={exportConversation}
              role="menuitem"
            >
              Export
            </button>
            <button
              className="conversation-menu-item conversation-menu-item-danger"
              data-testid="delete-conversation"
              onClick={remove}
              role="menuitem"
            >
              Delete
            </button>
          </div>
        )}
      </span>
    </div>
  );
}
