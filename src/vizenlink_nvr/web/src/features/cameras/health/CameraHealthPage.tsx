import React from "react";
import { useParams } from "react-router";
import { useCameras } from "@/lib/queries";
import { Forbidden } from "@/app/routes";
import { StatusBadge } from "@/components/StatusBadge";
import { HealthPanel } from "../HealthPanel";
import { useCameraHealth } from "../api";

export function CameraHealthPage() {
  const { serial = "" } = useParams<{ serial: string }>();
  const { data: rawCameras = [] } = useCameras();
  const { error, isError } = useCameraHealth(serial);

  if (isError && (error as any)?.status === 403) {
    return <Forbidden />;
  }

  const camera = rawCameras.find((c) => c.serial === serial);
  const isOnline = Boolean(camera?.is_online ?? camera?.state === "online");

  return (
    <div className="flex flex-col h-full w-full p-4 md:p-6 gap-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold text-foreground">
            {camera?.name || serial}
          </h1>
          <span className="text-xs text-muted-foreground font-mono">
            {serial}
          </span>
        </div>
        <StatusBadge
          kind={isOnline ? "online" : "offline"}
          label={isOnline ? "Online" : "Offline"}
        />
      </div>

      {/* Read-only Health Panel */}
      <HealthPanel serial={serial} />
    </div>
  );
}
