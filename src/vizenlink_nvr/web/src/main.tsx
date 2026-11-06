import "@fontsource-variable/inter";
import "./styles/globals.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router/dom";
import { router } from "./app/router";
import { queryClient } from "./lib/queries";
import { Toaster } from "./components/ui/sonner";
import { useUiStore, resolvedTheme } from "./stores/ui";
import { ThemeSync } from "./components/shell/ThemeSync";

function AppRoot() {
  const theme = useUiStore((s) => s.theme);
  return (
    <>
      <ThemeSync />
      <RouterProvider router={router} />
      <Toaster theme={resolvedTheme(theme)} />
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppRoot />
    </QueryClientProvider>
  </React.StrictMode>
);
