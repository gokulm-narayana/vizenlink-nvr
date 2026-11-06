import React, { useMemo } from "react";
import { useNavigate } from "react-router";
import { GalleryView } from "@/legacy/GalleryView";
import { useCameras, useCurrentUser } from "@/lib/queries";
import type { ShellRoute } from "@/app/routes";

function GalleryRouteAdapter() {
  const navigate = useNavigate();
  const { data: rawCameras = [] } = useCameras();
  const user = useCurrentUser();

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
    <GalleryView
      cameras={cameras}
      userRole={user?.role}
      onJumpToPlayback={handleJumpToPlayback}
    />
  );
}

export const routes: ShellRoute[] = [
  {
    path: "/gallery",
    title: "Gallery",
    minRole: "viewer",
    element: <GalleryRouteAdapter />,
  },
];
