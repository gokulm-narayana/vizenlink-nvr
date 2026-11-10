import React from "react";
import { LivePage } from "./LivePage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/",
    title: "Live View",
    minRole: "viewer",
    fullBleed: true,
    element: <LivePage />,
  },
  {
    path: "/live",
    title: "Live View",
    minRole: "viewer",
    fullBleed: true,
    element: <LivePage />,
  },
];
