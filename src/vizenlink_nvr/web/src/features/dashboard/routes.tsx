import React from "react";
import { DashboardPage } from "./DashboardPage";
import type { ShellRoute } from "@/app/routes";

// Phase 10: the Dashboard is the start page again (old VMS parity).
export const routes: ShellRoute[] = [
  {
    path: "/",
    title: "Dashboard",
    minRole: "viewer",
    element: <DashboardPage />,
  },
  {
    path: "/dashboard",
    title: "Dashboard",
    minRole: "viewer",
    element: <DashboardPage />,
  },
];
