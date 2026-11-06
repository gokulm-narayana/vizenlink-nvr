import React from "react";
import { DevicesPage } from "./DevicesPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/devices",
    title: "Mobile devices",
    minRole: "owner",
    element: <DevicesPage />,
  },
];
