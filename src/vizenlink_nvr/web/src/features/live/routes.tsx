import React from "react";
import { LivePage } from "./LivePage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/live",
    title: "Multiview",
    minRole: "viewer",
    fullBleed: true,
    element: <LivePage />,
  },
];
