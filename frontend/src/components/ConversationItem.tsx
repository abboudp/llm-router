import type { Conversation } from "../api/types";
import { relativeTime } from "../lib/time";
import { useApp } from "../state/store";

export function ConversationItem({ conversation }: { conversation: Conversation }) {
  const { state, actions } = useApp();
  const selected = state.selectedId === conversation.id;

  const rename = (event: React.MouseEvent) => {
    event.stopPropagation();
    const title = window.prompt("Rename conversation", conversation.title);
    if (title && title.trim() && title !== conversation.title) {
      void actions.rename(conversation.id, title.trim());
    }
  };

  const remove = (event: React.MouseEvent) => {
    event.stopPropagation();
    void actions.remove(conversation.id);
  };

  const togglePin = (event: React.MouseEvent) => {
    event.stopPropagation();
    void actions.setPinned(conversation.id, !conversation.pinned);
  };

  const exportConversation = (event: React.MouseEvent) => {
    event.stopPropagation();
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
      <span className="conversation-actions">
        <button
          className={`conversation-action pin-conversation${conversation.pinned ? " active" : ""}`}
          data-testid="pin-conversation"
          onClick={togglePin}
          aria-label={conversation.pinned ? "Unpin conversation" : "Pin conversation"}
          aria-pressed={conversation.pinned}
        >
          📌
        </button>
        <button
          className="conversation-action"
          data-testid="export-conversation"
          onClick={exportConversation}
          aria-label="Export conversation"
        >
          ⭳
        </button>
        <button
          className="conversation-action"
          data-testid="rename-conversation"
          onClick={rename}
          aria-label="Rename conversation"
        >
          ✎
        </button>
        <button
          className="conversation-action"
          data-testid="delete-conversation"
          onClick={remove}
          aria-label="Delete conversation"
        >
          🗑
        </button>
      </span>
    </div>
  );
}
