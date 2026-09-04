import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AppProvider } from "./state/store";
import "./styles/app.css";

const container = document.getElementById("root");
if (!container) throw new Error("root element missing");

createRoot(container).render(
  <AppProvider>
    <App />
  </AppProvider>,
);
