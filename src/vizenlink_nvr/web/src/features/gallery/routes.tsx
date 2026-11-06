import React from "react";
import { GalleryPage } from "./GalleryPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/gallery",
    title: "Gallery",
    minRole: "viewer",
    element: <GalleryPage />,
  },
];
