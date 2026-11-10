import React from "react";
import { EventsPage } from "./EventsPage";
import { EventDetailPage } from "./EventDetailPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/events",
    title: "Alerts",
    minRole: "viewer",
    element: <EventsPage />,
  },
  {
    path: "/events/:id",
    title: "Alert details",
    minRole: "viewer",
    element: <EventDetailPage />,
  },
];
