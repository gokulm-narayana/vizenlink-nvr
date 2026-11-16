import type { ShellRoute } from "@/app/routes";
import { UsersPage } from "../users/UsersPage";
import { DevicesPage } from "../devices/DevicesPage";
import { SettingsPage } from "./SettingsPage";
import { AuditLog } from "./AuditLog";
import { AiProvidersSettings } from "./AiProvidersSettings";
import { RecordingPage } from "./RecordingPage";
import { StoragePage } from "./StoragePage";

export const routes: ShellRoute[] = [
  { path: "/settings", title: "Settings", minRole: "viewer", element: <SettingsPage /> },
  { path: "/settings/recording", title: "Recording", minRole: "operator", element: <SettingsPage><RecordingPage /></SettingsPage> },
  { path: "/settings/storage", title: "Storage", minRole: "operator", element: <SettingsPage><StoragePage /></SettingsPage> },
  { path: "/settings/ai", title: "AI & API keys", minRole: "owner", element: <SettingsPage><AiProvidersSettings /></SettingsPage> },
  { path: "/settings/users", title: "Users", minRole: "owner", element: <SettingsPage><UsersPage /></SettingsPage> },
  { path: "/settings/devices", title: "Mobile devices", minRole: "owner", element: <SettingsPage><DevicesPage /></SettingsPage> },
  { path: "/settings/audit", title: "Audit log", minRole: "owner", element: <SettingsPage><AuditLog /></SettingsPage> },
];
