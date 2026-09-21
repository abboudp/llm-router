import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyTheme, resolveInitialTheme } from "./lib/theme";
import { AppProvider } from "./state/store";
import "./styles/app.css";

// Applied before the first render so there's no flash of the wrong theme.
applyTheme(resolveInitialTheme());

const container = document.getElementById("root");
if (!container) throw new Error("root element missing");

createRoot(container).render(
  <AppProvider>
    <App />
  </AppProvider>,
);
