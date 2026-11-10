import React, { useMemo } from "react";
import { useParams, useSearchParams, Link } from "react-router";
import { Cctv, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty";
import { InlineError } from "@/components/InlineError";
import { StatusBadge } from "@/components/StatusBadge";
import { useCameras, useCurrentUser, useRecordingStatus } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { CameraList } from "./CameraList";
import { IdentityTab } from "./tabs/IdentityTab";
import { VideoTab } from "./tabs/VideoTab";
import { ImageTab } from "./tabs/ImageTab";
import { OverlaysTab } from "./tabs/OverlaysTab";
import { HealthTab } from "./tabs/HealthTab";
import { MaintenanceTab } from "./tabs/MaintenanceTab";
import { useCameraSettings } from "./api";
import { CAMERAS_COPY } from "./copy";

export const CamerasPage: React.FC = () => {
  const { serial: serialParam } = useParams<{ serial?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const viewMode = useUiStore((s) => s.viewMode);
  const user = useCurrentUser();

  const {
    data: rawCameras = [],
    isLoading: camerasLoading,
    error: camerasError,
    refetch: refetchCameras,
  } = useCameras();

  const { data: recordingStatus = [] } = useRecordingStatus();

  const recordingSerials = useMemo(() => {
    return new Set(
      recordingStatus
        .filter((r) => r.is_recording === true)
        .map((r) => r.camera_serial)
    );
  }, [recordingStatus]);

  // Selected camera
  const selectedSerial = serialParam || rawCameras[0]?.serial || "";
  const selectedCamera = useMemo(() => {
    return rawCameras.find((c) => c.serial === selectedSerial) || rawCameras[0];
  }, [rawCameras, selectedSerial]);

  // Tab computation
  const tabParam = searchParams.get("tab") || "identity";
  const isAdvanced = true;

  const visibleTabs = useMemo(() => {
    if (isAdvanced) {
      return ["identity", "video", "image", "overlays", "health", "maintenance"];
    }
    return ["identity", "health"];
  }, [isAdvanced]);

  // If tabParam not in visibleTabs, fallback to identity
  const activeTab = useMemo(() => {
    if (visibleTabs.includes(tabParam)) {
      return tabParam;
    }
    return "identity";
  }, [tabParam, visibleTabs]);

  const handleTabChange = (newTab: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", newTab);
      return next;
    });
  };

  // Query settings for selected camera
  const {
    data: settings,
    isLoading: settingsLoading,
    error: settingsError,
    refetch: refetchSettings,
  } = useCameraSettings(selectedCamera?.serial);

  if (camerasLoading) {
    return (
      <div className="flex flex-col lg:flex-row gap-6 p-6 min-h-full">
        <div className="hidden lg:flex flex-col w-[280px] gap-2 border-r border-border pr-4">
          <Skeleton className="h-6 w-24 mb-2" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
        <div className="flex-1 flex flex-col gap-6">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  if (camerasError) {
    return (
      <div className="p-6">
        <InlineError
          message="Couldn't load cameras. Check your connection and try again."
          actionLabel="Reload cameras"
          onAction={() => void refetchCameras()}
        />
      </div>
    );
  }

  // Zero cameras: empty component replaces whole page
  if (rawCameras.length === 0) {
    return (
      <div className="p-6 min-h-full flex items-center justify-center">
        <Empty className="py-12 border border-border max-w-lg">
          <EmptyMedia variant="icon">
            <Cctv className="h-6 w-6 text-muted-foreground" />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{CAMERAS_COPY.EMPTY_HEADING}</EmptyTitle>
            <EmptyDescription>{CAMERAS_COPY.EMPTY_BODY}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild variant="default" size="sm">
              <Link to="/cameras/add">{CAMERAS_COPY.EMPTY_ACTION}</Link>
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    );
  }

  const isOnline =
    selectedCamera.is_online !== false &&
    selectedCamera.status !== "offline" &&
    selectedCamera.state !== "offline";
  const isRecording = recordingSerials.has(selectedCamera.serial);

  const isNotConnected =
    selectedCamera.state !== "active" &&
    selectedCamera.state !== "online" &&
    selectedCamera.status !== "online";
  const hasLastError = Boolean(selectedCamera.last_error);
  const showNotConnectedWarning = isNotConnected || hasLastError;

  return (
    <div className="flex flex-col lg:flex-row gap-6 min-h-full max-w-[1280px]">
      {/* Master List */}
      <CameraList cameras={rawCameras} selectedSerial={selectedCamera.serial} />

      {/* Detail Area */}
      <div className="flex-1 flex flex-col gap-6 min-w-0">
        {/* Detail Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
          <div className="flex flex-col gap-1 min-w-0">
            <h2 className="text-xl font-semibold text-foreground tracking-tight truncate">
              {selectedCamera.name}
            </h2>
            <span className="text-xs font-mono text-muted-foreground">
              {selectedCamera.serial}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge kind={isOnline ? "online" : "offline"} />
            {isRecording ? <StatusBadge kind="recording" /> : <span className="text-xs text-muted-foreground">Recording policy: {recordingStatus.find(r => r.camera_serial === selectedCamera.serial)?.mode || "unknown"}</span>}
          </div>
        </div>

        {/* Not-connected / last_error warning alert */}
        {showNotConnectedWarning && (
          <Alert variant="default" className="border-warning/40 bg-warning-subtle text-foreground flex flex-col gap-2 p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-2">
                <TriangleAlert className="h-4 w-4 shrink-0 text-warning mt-0.5" />
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-foreground">
                    {CAMERAS_COPY.NOT_CONNECTED_TITLE(selectedCamera.name)}
                  </span>
                  {selectedCamera.last_error && (
                    <p className="text-xs font-mono text-muted-foreground break-all">
                      {selectedCamera.last_error}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {CAMERAS_COPY.NOT_CONNECTED_BODY}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0 text-xs h-8"
                onClick={() => handleTabChange("identity")}
              >
                {CAMERAS_COPY.EDIT_DETAILS}
              </Button>
            </div>
          </Alert>
        )}

        {/* Tab Navigation */}
        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="w-full justify-start overflow-x-auto border-b border-border bg-transparent p-0 rounded-none h-auto gap-2">
            <TabsTrigger
              value="identity"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
            >
              Details
            </TabsTrigger>

            {isAdvanced && (
              <>
                <TabsTrigger
                  value="video"
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
                >
                  Video
                </TabsTrigger>
                <TabsTrigger
                  value="image"
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
                >
                  Image
                </TabsTrigger>
                <TabsTrigger
                  value="overlays"
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
                >
                  On-screen text
                </TabsTrigger>
              </>
            )}

            <TabsTrigger
              value="health"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
            >
              Health
            </TabsTrigger>

            {isAdvanced && (
              <TabsTrigger
                value="maintenance"
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none text-xs px-4 py-2"
              >
                Maintenance
              </TabsTrigger>
            )}
          </TabsList>
        </Tabs>

        {/* Tab Panels */}
        {activeTab === "maintenance" ? (
          <MaintenanceTab
            serial={selectedCamera.serial}
            cameraName={selectedCamera.name}
          />
        ) : activeTab === "health" ? (
          <HealthTab serial={selectedSerial} />
        ) : settingsLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : settingsError ? (
          <InlineError
            message="Couldn't load camera settings. Check your connection and try again."
            actionLabel="Reload settings"
            onAction={() => void refetchSettings()}
          />
        ) : settings ? (
          <>
            {activeTab === "identity" && (
              <IdentityTab
                serial={selectedCamera.serial}
                cameraName={selectedCamera.name}
                settings={settings}
              />
            )}
            {activeTab === "video" && (
              <VideoTab
                serial={selectedCamera.serial}
                cameraName={selectedCamera.name}
                settings={settings}
              />
            )}
            {activeTab === "image" && (
              <ImageTab
                serial={selectedCamera.serial}
                cameraName={selectedCamera.name}
                settings={settings}
              />
            )}
            {activeTab === "overlays" && (
              <OverlaysTab
                serial={selectedCamera.serial}
                cameraName={selectedCamera.name}
                settings={settings}
              />
            )}
          </>
        ) : null}
      </div>
    </div>
  );
};
