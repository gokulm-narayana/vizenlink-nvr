import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Cctv } from "lucide-react";
import { useCameras, useRecordingStatus, useCurrentUser } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { GridStorage, type GridDimension } from "@/services/grid_storage";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
  EmptyMedia,
} from "@/components/ui/empty";
import { cn } from "cn";
import { LiveToolbar } from "./LiveToolbar";
import { VideoTile } from "./VideoTile";
import { LIVE_COPY } from "./copy";

export const LivePage: React.FC = () => {
  const { data: rawCameras = [] } = useCameras();
  const { data: recList = [] } = useRecordingStatus();
  const user = useCurrentUser();
  const viewMode = useUiStore((s) => s.viewMode);

  const [dimension, setDimension] = useState<GridDimension>(2);
  const [page, setPage] = useState<number>(0);
  const [maximizedSerial, setMaximizedSerial] = useState<string | null>(null);

  // Load layout on mount
  useEffect(() => {
    const rawStorage = localStorage.getItem("vizenlink_nvr_grid_layout_v1");
    // If no stored layout and exactly 1 camera, default dimension is 1
    const defaultDim = !rawStorage && rawCameras.length === 1 ? 1 : 2;
    const saved = GridStorage.load(defaultDim);
    setDimension(saved.dimension);
    setPage(saved.page);
  }, [rawCameras.length]);

  // Persist layout changes
  const handleDimensionChange = (dim: GridDimension) => {
    setDimension(dim);
    setPage(0);
    GridStorage.save({
      dimension: dim,
      page: 0,
      slotAssignments: {},
    });
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    GridStorage.save({
      dimension,
      page: newPage,
      slotAssignments: {},
    });
  };

  const recordingSerials = useMemo(() => {
    const active = new Set<string>();
    for (const item of recList) {
      if (item.mode === "continuous" || item.mode === "scheduled" || item.mode === "event") {
        active.add(item.camera_serial);
      }
    }
    return active;
  }, [recList]);

  // In simple view, 4x4 renders as 3x3 without modifying stored preference
  const effectiveDimension: GridDimension =
    viewMode === "simple" && dimension === 4 ? 3 : dimension;

  const tilesPerPage = effectiveDimension * effectiveDimension;
  const totalPages = Math.max(1, Math.ceil(rawCameras.length / tilesPerPage));
  const currentPage = Math.min(page, totalPages - 1);

  const startIdx = currentPage * tilesPerPage;
  const visibleCameras = rawCameras.slice(startIdx, startIdx + tilesPerPage);

  // Zero cameras empty state
  if (rawCameras.length === 0) {
    const isManager = user?.role === "operator" || user?.role === "owner";
    return (
      <div className="flex h-[calc(100dvh-56px)] w-full items-center justify-center p-6">
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Cctv className="h-6 w-6" />
            </EmptyMedia>
            <EmptyTitle>
              {isManager
                ? LIVE_COPY.EMPTY_HEADING_OPERATOR
                : LIVE_COPY.EMPTY_HEADING_VIEWER}
            </EmptyTitle>
            <EmptyDescription className="text-sm font-normal max-w-md">
              {isManager
                ? LIVE_COPY.EMPTY_BODY_OPERATOR
                : LIVE_COPY.EMPTY_BODY_VIEWER}
            </EmptyDescription>
          </EmptyHeader>
          {isManager && (
            <EmptyContent>
              <Button asChild>
                <Link to="/cameras/add">{LIVE_COPY.EMPTY_ACTION_ADD}</Link>
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    );
  }

  // Maximized single tile
  if (maximizedSerial) {
    const cam = rawCameras.find((c) => c.serial === maximizedSerial);
    return (
      <div className="flex flex-col h-[calc(100dvh-56px)] w-full bg-background p-4 overflow-hidden">
        {cam && (
          <VideoTile
            serial={cam.serial}
            name={cam.name}
            isRecording={recordingSerials.has(cam.serial)}
            isMaximized={true}
            lastSeenAt={cam.last_seen_at}
            viewMode={viewMode}
            onToggleMaximize={() => setMaximizedSerial(null)}
          />
        )}
      </div>
    );
  }

  const gridColsClass =
    effectiveDimension === 1
      ? "grid-cols-1"
      : effectiveDimension === 2
        ? "grid-cols-1 sm:grid-cols-2"
        : effectiveDimension === 3
          ? "grid-cols-1 sm:grid-cols-2 md:grid-cols-3"
          : "grid-cols-1 sm:grid-cols-2 md:grid-cols-4";

  const gapClass = effectiveDimension === 4 ? "gap-1" : "gap-2";

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <LiveToolbar
        dimension={dimension}
        onDimensionChange={handleDimensionChange}
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={handlePageChange}
        totalCameras={rawCameras.length}
        viewMode={viewMode}
      />

      <div className="flex-1 overflow-y-auto p-4">
        <div className={cn("grid w-full", gridColsClass, gapClass)}>
          {visibleCameras.map((cam) => (
            <VideoTile
              key={cam.serial}
              serial={cam.serial}
              name={cam.name}
              isRecording={recordingSerials.has(cam.serial)}
              isMaximized={false}
              lastSeenAt={cam.last_seen_at}
              viewMode={viewMode}
              onToggleMaximize={() => setMaximizedSerial(cam.serial)}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default LivePage;
