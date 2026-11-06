import React, { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { PlaybackView } from "@/legacy/PlaybackView";
import { useCameras } from "@/lib/queries";
import type { ShellRoute } from "@/app/routes";

function PlaybackRouteAdapter() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: rawCameras = [] } = useCameras();

  const cameras = useMemo(
    () => rawCameras.map((c) => ({ serial: c.serial, name: c.name })),
    [rawCameras]
  );

  const initialCameraSerial = searchParams.get("camera") || undefined;
  const initialTimestamp = searchParams.get("t") || undefined;

  const handleOpenGallery = () => {
    void navigate("/gallery?tab=clips");
  };

  return (
    <PlaybackView
      cameras={cameras}
      initialCameraSerial={initialCameraSerial}
      initialTimestamp={initialTimestamp}
      onOpenGallery={handleOpenGallery}
    />
  );
}

export const routes: ShellRoute[] = [
  {
    path: "/playback",
    title: "Playback",
    minRole: "viewer",
    fullBleed: true,
    element: <PlaybackRouteAdapter />,
  },
];
