import React from "react";
import { AddCameraPage } from "./AddCameraPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/cameras/add",
    title: "Add camera",
    minRole: "operator",
    element: <AddCameraPage />,
  },
];
