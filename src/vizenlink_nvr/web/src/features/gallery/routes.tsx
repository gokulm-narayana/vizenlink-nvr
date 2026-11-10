import React from "react";
import { GalleryPage } from "./GalleryPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/gallery",
    title: "Saved Media",
    minRole: "viewer",
    element: <GalleryPage />,
  },
];
