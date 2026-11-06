import React from "react";
import { ProfilePage } from "./ProfilePage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/profile",
    title: "Profile",
    minRole: "viewer",
    element: <ProfilePage />,
  },
];
