import React from "react";
import { DashboardPage } from "./DashboardPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/dashboard",
    title: "System Health",
    minRole: "viewer",
    element: <DashboardPage />,
  },
];
