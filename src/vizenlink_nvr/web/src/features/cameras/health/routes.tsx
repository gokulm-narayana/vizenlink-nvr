import React from "react";
import { CameraHealthPage } from "./CameraHealthPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/cameras/:serial/health",
    title: "Camera health",
    minRole: "viewer",
    element: <CameraHealthPage />,
  },
];
