import React from "react";
import { EventsPage } from "./EventsPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/events",
    title: "Events",
    minRole: "viewer",
    element: <EventsPage />,
  },
];