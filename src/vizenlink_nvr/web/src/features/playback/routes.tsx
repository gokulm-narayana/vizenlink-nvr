import React from "react";
import { PlaybackPage } from "./PlaybackPage";
import { ComparePlaybackPage } from "./ComparePlaybackPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  { path: "/playback/compare", title: "Compare Playback", minRole: "viewer", fullBleed: true, element: <ComparePlaybackPage /> },
  {
    path: "/playback",
    title: "Playback",
    minRole: "viewer",
    fullBleed: true,
    element: <PlaybackPage />,
  },
];
