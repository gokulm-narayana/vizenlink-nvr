import React, { useMemo } from "react";
import { Dashboard } from "@/legacy/Dashboard";
import { useRecordingStatus } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import type { ShellRoute } from "@/app/routes";

function DashboardRouteAdapter() {
  const viewMode = useUiStore((s) => s.viewMode);
  const { data: recList = [] } = useRecordingStatus();

  const recordingCount = useMemo(() => {
    const activeSerials = new Set<string>();
    for (const item of recList) {
      if (item.mode === "continuous" || item.mode === "scheduled" || item.mode === "event") {
        activeSerials.add(item.camera_serial);
      }
    }
    return activeSerials.size;
  }, [recList]);

  return <Dashboard viewMode={viewMode} recordingCount={recordingCount} />;
}

export const routes: ShellRoute[] = [
  {
    path: "/dashboard",
    title: "Dashboard",
    minRole: "viewer",
    element: <DashboardRouteAdapter />,
  },
];
