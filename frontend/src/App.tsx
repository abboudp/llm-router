import { useEffect } from "react";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { ErrorToast } from "./components/ErrorToast";
import { ShortcutsModal } from "./components/ShortcutsModal";
import { Sidebar } from "./components/Sidebar";
import { Thread } from "./components/Thread";
import { isNewConversationHotkey } from "./lib/keyboard";
import { useApp } from "./state/store";

export function App() {
  const { state, actions } = useApp();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isNewConversationHotkey(event)) {
        event.preventDefault();
        void actions.newConversation();
        return;
      }
      if (event.key === "Escape") {
        if (state.shortcutsOpen) actions.closeShortcuts();
        else if (state.error) actions.dismissError();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.shortcutsOpen, state.error]);

  return (
    <div className="app">
      <Sidebar />
      <div className="main-column">
        {state.selectedId == null ? (
          <EmptyState />
        ) : (
          <>
            <Thread />
            <Composer />
          </>
        )}
      </div>
      <ErrorToast />
      <ShortcutsModal />
    </div>
  );
}
