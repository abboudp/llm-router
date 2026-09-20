import type { Conversation } from "../api/types";
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

  return (
    <div
      className={`conversation-item${selected ? " selected" : ""}`}
      data-testid="conversation-item"
      onClick={() => void actions.select(conversation.id)}
    >
      <span className="conversation-title">{conversation.title}</span>
      <span className="conversation-actions">
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
