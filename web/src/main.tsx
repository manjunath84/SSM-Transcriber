import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import { loadConfig } from "./config";
import "./index.css";

const queryClient = new QueryClient();

// Load runtime config (/config.json, written by `cdk deploy`) BEFORE
// rendering so any getConfig() call site (auth.ts / api.ts) sees a
// populated config. Top-level await is valid in Vite's ESM output.
await loadConfig();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
