import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";

import { App } from "./app/App";
import "./styles/custom.css";
import "./styles/landing.css";

export function mountApp(rootElement: HTMLElement): Root {
  const root = createRoot(rootElement);
  root.render(
    <StrictMode>
      <App />
    </StrictMode>
  );
  return root;
}

export const appRoot = mountApp(document.getElementById("root")!);
