import React, { useMemo } from "react";
import { CameraSettingsView } from "@/legacy/CameraSettingsView";
import { useCameras, useCurrentUser } from "@/lib/queries";
import type { ShellRoute } from "@/app/routes";

function CamerasRouteAdapter() {
  const { data: rawCameras = [] } = useCameras();
  const user = useCurrentUser();

  const cameras = useMemo(
    () =>
      rawCameras.map((c) => ({
        serial: c.serial,
        name: c.name,
        state: c.state || c.status || "online",
      })),
    [rawCameras]
  );

  return <CameraSettingsView cameras={cameras} userRole={user?.role} />;
}

export const routes: ShellRoute[] = [
  {
    path: "/cameras",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasRouteAdapter />,
  },
  {
    path: "/cameras/:serial",
    title: "Cameras",
    minRole: "operator",
    element: <CamerasRouteAdapter />,
  },
];
