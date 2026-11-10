import type { ShellRoute } from "@/app/routes";
import { SettingsPage } from "./SettingsPage";
import { RecordingPage } from "./RecordingPage";
export const routes: ShellRoute[] = [
  { path: "/settings", title: "Settings", minRole: "viewer", element: <SettingsPage /> },
  { path: "/settings/recording", title: "Recording & Storage", minRole: "operator", element: <RecordingPage /> },
];
