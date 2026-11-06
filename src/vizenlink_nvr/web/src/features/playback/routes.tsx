import React from "react";
import { PlaybackPage } from "./PlaybackPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/playback",
    title: "Playback",
    minRole: "viewer",
    fullBleed: true,
    element: <PlaybackPage />,
  },
];
