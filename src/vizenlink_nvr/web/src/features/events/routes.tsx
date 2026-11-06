import React, { useMemo } from "react";
import { useNavigate } from "react-router";
import { EventFeed } from "@/legacy/EventFeed";
import { useCameras } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import type { ShellRoute } from "@/app/routes";

function EventsRouteAdapter() {
  const navigate = useNavigate();
  const { data: rawCameras = [] } = useCameras();
  const readEventIds = useUiStore((s) => s.readEventIds);
  const markEventRead = useUiStore((s) => s.markEventRead);

  const cameras = useMemo(
    () => rawCameras.map((c) => ({ serial: c.serial, name: c.name })),
    [rawCameras]
  );

  const handleJumpToPlayback = (cameraSerial: string, timestamp: string) => {
    void navigate(
      `/playback?camera=${encodeURIComponent(cameraSerial)}&t=${encodeURIComponent(timestamp)}`
    );
  };

  return (
    <EventFeed
      cameras={cameras}
      readEventIds={readEventIds}
      onEventRead={markEventRead}
      onJumpToPlayback={handleJumpToPlayback}
    />
  );
}

export const routes: ShellRoute[] = [
  {
    path: "/events",
    title: "Events",
    minRole: "viewer",
    element: <EventsRouteAdapter />,
  },
];
