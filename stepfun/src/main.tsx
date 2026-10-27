import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ModelProvider } from "./model/ModelContext.tsx";
import Spike from "./spike/Spike.tsx";

const isSpike = window.location.pathname.replace(/\/$/, "") === "/spike";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isSpike ? (
      <Spike />
    ) : (
      <ModelProvider>
        <App />
      </ModelProvider>
    )}
  </StrictMode>,
);
