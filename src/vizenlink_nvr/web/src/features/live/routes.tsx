import React, { useMemo } from "react";
import { LiveGrid } from "@/legacy/LiveGrid";
import { useCameras, useRecordingStatus } from "@/lib/queries";
import type { ShellRoute } from "@/app/routes";

function LiveRouteAdapter() {
  const { data: cameras = [] } = useCameras();
  const { data: recList = [] } = useRecordingStatus();

  const recordingSerials = useMemo(() => {
    const activeRecs = new Set<string>();
    for (const item of recList) {
      if (item.mode === "continuous" || item.mode === "scheduled" || item.mode === "event") {
        activeRecs.add(item.camera_serial);
      }
    }
    return activeRecs;
  }, [recList]);

  const liveCameras = useMemo(() => {
    return cameras.map((c) => ({
      serial: c.serial,
      name: c.name,
      state: c.state || c.status || "online",
    }));
  }, [cameras]);

  return <LiveGrid cameras={liveCameras} recordingSerials={recordingSerials} />;
}

export const routes: ShellRoute[] = [
  {
    path: "/",
    title: "Live",
    minRole: "viewer",
    fullBleed: true,
    element: <LiveRouteAdapter />,
  },
  {
    path: "/live",
    title: "Live",
    minRole: "viewer",
    fullBleed: true,
    element: <LiveRouteAdapter />,
  },
];
