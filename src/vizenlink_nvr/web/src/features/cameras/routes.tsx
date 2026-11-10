import React from "react";
import { CamerasPage } from "./CamerasPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/cameras",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasPage />,
  },
  {
    path: "/cameras/:serial",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasPage />,
  },
];