import { useApp } from "../state/store";
import { ConversationItem } from "./ConversationItem";
import { SettingsPanel } from "./SettingsPanel";

export function Sidebar() {
  const { state, actions } = useApp();

  return (
    <div className="sidebar" data-testid="sidebar">
      <button
        className="new-conversation"
        data-testid="new-conversation"
        onClick={() => void actions.newConversation()}
      >
        + New chat
      </button>
      <div className="conversation-list">
        {state.conversations.map((conversation) => (
          <ConversationItem key={conversation.id} conversation={conversation} />
        ))}
      </div>
      <div className="sidebar-footer">
        <SettingsPanel />
      </div>
    </div>
  );
}
