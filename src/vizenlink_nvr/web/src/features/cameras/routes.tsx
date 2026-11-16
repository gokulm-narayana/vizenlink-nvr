import React from "react";
import { CamerasPage } from "./CamerasPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/cameras",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasPage />,
    stickyContent: true,
  },
  {
    path: "/cameras/:serial",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasPage />,
    // The settings menu stays in place while the section scrolls (needs a non-scrolling <main>).
    stickyContent: true,
  },
];