import "@fontsource-variable/inter";
import "./styles/globals.css";
import React from "react";
import ReactDOM from "react-dom/client";
import LegacyApp from "./legacy/LegacyApp";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <LegacyApp />
  </React.StrictMode>
);
