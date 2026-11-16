import { isCameraOffline } from "@/lib/recorder-status";
import React, { useMemo } from "react";
import { useParams, useSearchParams, Link } from "react-router";
import { Cctv, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CameraSettingsNav, SETTINGS_SECTION_IDS, sectionLabel } from "./CameraSettingsNav";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty";
import { InlineError } from "@/components/InlineError";
import { StatusBadge } from "@/components/StatusBadge";
import { useCameras, useCurrentUser, useRecordingStatus } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { ApiError } from "@/lib/api";
import { CameraList } from "./CameraList";
import { IdentityTab } from "./tabs/IdentityTab";
import { VideoTab } from "./tabs/VideoTab";
import { ImageTab } from "./tabs/ImageTab";
import { OverlaysTab } from "./tabs/OverlaysTab";
import { HealthTab } from "./tabs/HealthTab";
import { MaintenanceTab } from "./tabs/MaintenanceTab";
import { useCameraSettings } from "./api";
import { CAMERAS_COPY } from "./copy";
import { CameraOverview } from "./CameraOverview";
import { CameraFeaturesTab, CAMERA_FEATURE_TABS } from "./CameraFeaturesTab";
import { ZonePreview } from "./PrivacyZones";

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
    return serialParam ? rawCameras.find((c) => c.serial === selectedSerial) : rawCameras[0];
  }, [rawCameras, selectedSerial, serialParam]);

  // Tab computation
  const tabParam = searchParams.get("tab") || "identity";
  const isAdvanced = true;

  const visibleTabs = useMemo(() => {
    if (isAdvanced) {
      return SETTINGS_SECTION_IDS;
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
  const preview = searchParams.get("preview");
  const detectionPreview = activeTab === "detection" && preview === "detection";
  const personZonePreview = activeTab === "detection" && preview === "person-zones";
  const privacyPreview = activeTab === "privacy" && preview === "privacy";

  const handleTabChange = (newTab: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", newTab);
      if (newTab !== activeTab) next.delete("preview");
      return next;
    });
  };

  // Query settings for selected camera
  const readsLiveSettings = Boolean(serialParam) && ["identity", "video", "image", "overlays"].includes(activeTab);
  const {
    data: settings,
    isLoading: settingsLoading,
    isFetching: settingsFetching,
    error: settingsError,
    refetch: refetchSettings,
  } = useCameraSettings(selectedCamera?.serial, readsLiveSettings);

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

  // Same rule as the Dashboard (registry state "active" = reachable).
  if (!serialParam) return <CameraOverview cameras={rawCameras} recordings={recordingStatus} />;

  if (!selectedCamera) return <div className="p-6"><p className="text-sm">This camera is unavailable or you no longer have access.</p><Link to="/cameras" className="text-sm text-primary-text">Return to cameras</Link></div>;

  const isOnline = !isCameraOffline(selectedCamera);
  const settingsUnavailable = readsLiveSettings && Boolean(settingsError);
  const settingsStatus = settingsError instanceof ApiError ? settingsError.status : undefined;
  const settingsMessage = settingsStatus === 503
    ? "The recorder could not load the camera credentials. Check that the recorder is using the data directory and credential vault where the camera was added."
    : !isOnline || settingsStatus === 502 || settingsStatus === 504
      ? "The recorder couldn't read live settings from this camera. Check the camera's power and network connection, then reload settings."
      : "The recorder couldn't load these settings. Open Health for device information or reload settings to try again.";
  const isRecording = recordingSerials.has(selectedCamera.serial);

  const isNotConnected =
    selectedCamera.state !== "active" &&
    selectedCamera.state !== "online" &&
    selectedCamera.status !== "online";
  const hasLastError = Boolean(selectedCamera.last_error);
  const showNotConnectedWarning = isNotConnected || hasLastError;

  return (
    <div className="flex flex-col lg:flex-row gap-6 min-h-full max-w-[1440px]">
      {/* Master List */}
      <CameraList cameras={rawCameras} selectedSerial={selectedCamera.serial} />

      {/* Detail Area */}
      <div className="flex-1 flex flex-col gap-6 min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2"><Link to="/cameras" className="text-sm text-primary-text hover:underline">← All cameras</Link><Button variant="outline" size="sm" asChild><Link to={`/live?camera=${encodeURIComponent(selectedCamera.serial)}`}>Open live view</Link></Button></div>
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
            {detectionPreview || personZonePreview || privacyPreview ? <StatusBadge kind="degraded" label="Settings preview" /> : <StatusBadge
              kind={isOnline ? (settingsUnavailable ? "degraded" : "online") : "offline"}
              label={isOnline && settingsUnavailable ? "Settings unavailable" : undefined}
            />}
            {isRecording ? <StatusBadge kind="recording" /> : <span className="text-xs text-muted-foreground">{recordingStatus.find(r => r.camera_serial === selectedCamera.serial)?.mode === "off" ? "Recording off" : "Not recording"}</span>}
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

        {/* One grouped settings menu (left on wide screens, dropdown on narrow) */}
        <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <CameraSettingsNav active={activeTab} onChange={handleTabChange} />
        <div className="flex min-w-0 flex-col gap-6" role="tabpanel" aria-label={sectionLabel(activeTab)}>

        {/* Tab Panels */}
        {activeTab === "maintenance" ? (
          <MaintenanceTab
            serial={selectedCamera.serial}
            cameraName={selectedCamera.name}
          />
        ) : activeTab === "health" ? (
          <HealthTab serial={selectedSerial} />
        ) : CAMERA_FEATURE_TABS.some(t => t.id === activeTab) ? (
          <>
            {personZonePreview || privacyPreview ? (
              <ZonePreview key={`${selectedSerial}-${preview}`} kind={personZonePreview ? "person" : "privacy"} />
            ) : (
              <CameraFeaturesTab serial={selectedCamera.serial} cameraName={selectedCamera.name} group={activeTab} preview={detectionPreview} />
            )}
          </>
        ) : settingsLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : settingsError ? (
          <>
            {!showNotConnectedWarning && (
              <InlineError
                title="Live settings unavailable"
                message={settingsMessage}
                actionLabel="Reload settings"
                onAction={() => void refetchSettings()}
                pending={settingsFetching}
              />
            )}
            {activeTab === "identity" && (
              <section className="rounded-xl border border-border bg-card p-6" aria-labelledby="saved-camera-details">
                <h3 id="saved-camera-details" className="font-semibold">Saved camera details</h3>
                <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
                  <div><dt className="text-muted-foreground">Name</dt><dd>{selectedCamera.name}</dd></div>
                  <div><dt className="text-muted-foreground">Serial number</dt><dd className="font-mono">{selectedCamera.serial}</dd></div>
                  <div><dt className="text-muted-foreground">Location</dt><dd>{selectedCamera.location || "—"}</dd></div>
                </dl>
              </section>
            )}
            <div className="flex flex-wrap gap-2">
              {showNotConnectedWarning && (
                <Button type="button" variant="outline" onClick={() => void refetchSettings()} disabled={settingsFetching}>
                  {settingsFetching ? "Reloading…" : "Reload settings"}
                </Button>
              )}
              <Button type="button" variant="outline" onClick={() => handleTabChange("health")}>Open camera health</Button>
            </div>
          </>
        ) : settings?.unavailable_sections?.includes(activeTab) ? (
          <InlineError message={settings.read_errors?.[activeTab] || "Camera values could not be read."} actionLabel="Reload settings" onAction={() => void refetchSettings()} />
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
      </div>
    </div>
  );
};
