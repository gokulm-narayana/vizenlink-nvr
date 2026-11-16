import React from "react";
import { ProfilePage } from "./ProfilePage";
import { SettingsPage } from "../settings/SettingsPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/profile",
    title: "Profile",
    minRole: "viewer",
    // Shown inside the Settings layout so "My Account" keeps the settings menu beside it.
    element: <SettingsPage><ProfilePage /></SettingsPage>,
  },
];
