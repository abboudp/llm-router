import { useEffect, useRef, useState } from "react";
import { isEditableTarget } from "../lib/keyboard";
import { useApp } from "../state/store";
import { ConversationItem } from "./ConversationItem";
import { ThemeToggle } from "./ThemeToggle";

const SEARCH_DEBOUNCE_MS = 250;

export function Sidebar() {
  const { state, actions } = useApp();
  const [query, setQuery] = useState(state.searchQuery);
  const skipNextSearch = useRef(true);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (skipNextSearch.current) {
      skipNextSearch.current = false;
      return;
    }
    const timer = window.setTimeout(() => void actions.search(query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    const focusSearchHotkey = (event: KeyboardEvent) => {
      if (event.key !== "/" || isEditableTarget(event.target)) return;
      event.preventDefault();
      searchInputRef.current?.focus();
    };
    window.addEventListener("keydown", focusSearchHotkey);
    return () => window.removeEventListener("keydown", focusSearchHotkey);
  }, []);

  return (
    <div className="sidebar" data-testid="sidebar">
      <button
        className="new-conversation"
        data-testid="new-conversation"
        disabled={state.creatingConversation}
        onClick={() => void actions.newConversation()}
      >
        + New chat
      </button>
      <input
        ref={searchInputRef}
        className="conversation-search"
        data-testid="conversation-search"
        type="search"
        placeholder="Search conversations… (press / to focus)"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="conversation-list">
        {state.conversations.length === 0 && query.trim() ? (
          <p className="conversation-search-empty" data-testid="conversation-search-empty">
            No conversations match &ldquo;{query.trim()}&rdquo;.
          </p>
        ) : (
          state.conversations.map((conversation) => (
            <ConversationItem key={conversation.id} conversation={conversation} />
          ))
        )}
      </div>
      <div className="sidebar-footer">
        <ThemeToggle />
      </div>
    </div>
  );
}
