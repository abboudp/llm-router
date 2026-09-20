import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { ErrorToast } from "./components/ErrorToast";
import { Sidebar } from "./components/Sidebar";
import { Thread } from "./components/Thread";
import { useApp } from "./state/store";

export function App() {
  const { state } = useApp();

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
    </div>
  );
}
