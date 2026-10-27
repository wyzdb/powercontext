import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import BenchRun from "./benchrun/BenchRun.tsx";
import { ModelProvider } from "./model/ModelContext.tsx";
import Spike from "./spike/Spike.tsx";

const path = window.location.pathname.replace(/\/$/, "");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {path === "/spike" ? (
      <Spike />
    ) : path === "/benchrun" ? (
      <BenchRun />
    ) : (
      <ModelProvider>
        <App />
      </ModelProvider>
    )}
  </StrictMode>,
);
