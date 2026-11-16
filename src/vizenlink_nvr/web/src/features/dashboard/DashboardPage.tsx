import React, { useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Cctv,
  HardDrive,
  Cpu,
  Server,
  CircleCheck,
  TriangleAlert,
  OctagonAlert,
  Bell,
  History,
  ArrowUpRight,
  Video,
  Disc,
  Clock,
  Search,
  X,
  LayoutGrid,
  Columns2,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { InlineError } from "@/components/InlineError";
import { CameraHealthLink } from "@/components/CameraHealthLink";
import {
  useAlerts,
  useCameras,
  useCurrentUser,
  useHealth,
  useRecordingStatus,
  useUnreadCount,
  type CameraInfo,
  type RecordingStatusItem,
} from "@/lib/queries";
import { formatDateTime, formatRelative, useSiteTimeZone } from "@/lib/time";
import { evaluateRecorderStatus, isCameraOffline, recordingSerials as toRecordingSerials } from "@/lib/recorder-status";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";
import { useOutages, useStorageStatus, useSystemMetrics } from "./api";
import { bytesToGiB, storageSummary } from "./StorageCard";
import { OutageHistoryDialog } from "./OutageHistoryDialog";
import { DASHBOARD_COPY } from "./copy";
import { PageIntro } from "@/components/PageIntro";

export function formatUptime(seconds?: number): string {
  if (!seconds || seconds <= 0) return "0s";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

/* ------------------------------------------------------------------------- */
/* Camera rows: one list, problems first                                      */
/* ------------------------------------------------------------------------- */

export type CameraRowState = "offline" | "not_recording" | "disabled" | "ok";

export interface CameraRow {
  camera: CameraInfo;
  state: CameraRowState;
  online: boolean;
  recording: boolean;
  problem: string | null;
  lastFootage: string | null;
}

const ROW_ORDER: Record<CameraRowState, number> = { offline: 0, not_recording: 1, disabled: 2, ok: 3 };

export function buildCameraRows(
  cameras: CameraInfo[],
  recList: RecordingStatusItem[],
  openOutages: Map<string, string>,
  storageBroken: boolean
): CameraRow[] {
  const rec = new Map(recList.map((r) => [r.camera_serial, r]));
  const recording = toRecordingSerials(recList);
  const outageSerials = new Set(openOutages.keys());
  const rows = cameras.map((camera): CameraRow => {
    const r = rec.get(camera.serial);
    const online = !isCameraOffline(camera, outageSerials);
    const isRec = !storageBroken && recording.has(camera.serial);
    const lastFootage = r?.last_segment_at ?? null;
    if (!online) {
      const problem =
        camera.state === "auth_failed"
          ? "Camera rejected the saved password"
          : camera.state === "tls_changed"
            ? "Camera security certificate changed"
            : "Camera offline";
      return { camera, state: "offline", online, recording: isRec, problem, lastFootage };
    }
    if (r?.mode === "off") return { camera, state: "disabled", online, recording: false, problem: null, lastFootage };
    if (!isRec) {
      return {
        camera,
        state: "not_recording",
        online,
        recording: false,
        problem: storageBroken ? "Not recording: storage unavailable" : "Not recording",
        lastFootage,
      };
    }
    return { camera, state: "ok", online, recording: true, problem: null, lastFootage };
  });
  return rows.sort((a, b) => ROW_ORDER[a.state] - ROW_ORDER[b.state] || a.camera.name.localeCompare(b.camera.name));
}

/* ------------------------------------------------------------------------- */
/* Building blocks                                                            */
/* ------------------------------------------------------------------------- */

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint?: string;
  tone: "ok" | "warning" | "critical" | "neutral";
}) {
  return (
    <Card data-kpi={label} className="min-w-0 gap-0 py-0">
      <CardContent className="flex items-start gap-4 p-4">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-lg",
            tone === "ok" && "bg-success-subtle text-success",
            tone === "warning" && "bg-warning-subtle text-warning",
            tone === "critical" && "bg-critical-subtle text-critical",
            tone === "neutral" && "bg-selected text-primary-text"
          )}
        >
          <Icon className="size-5" />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm text-muted-foreground">{label}</span>
          {/* Kept out of cn(): tailwind-merge would drop the custom text-display size. */}
          <span className={"text-display font-semibold tabular-nums " + (tone === "critical" ? "text-critical" : "text-foreground")}>
            {value}
          </span>
          {hint && <span className="truncate text-xs text-muted-foreground">{hint}</span>}
        </span>
      </CardContent>
    </Card>
  );
}

function Panel({
  icon: Icon,
  title,
  action,
  children,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("min-w-0 gap-0 py-0", className)}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-semibold">
          <Icon className="size-4 shrink-0 text-primary-text" />
          <span className="truncate">{title}</span>
        </CardTitle>
        {action}
      </CardHeader>
      <CardContent className="flex flex-col gap-4 p-4">{children}</CardContent>
    </Card>
  );
}

function Meter({ label, percent, caption }: { label: string; percent: number | null; caption?: string }) {
  const p = percent == null ? 0 : Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-semibold tabular-nums">{percent == null ? "–" : `${p}%`}</span>
      </div>
      <Progress
        value={p}
        aria-label={`${label} ${p}%`}
        className={cn(
          "h-2 w-full bg-muted",
          p > 90
            ? "[&_[data-slot=progress-indicator]]:bg-critical"
            : p >= 80
              ? "[&_[data-slot=progress-indicator]]:bg-warning"
              : "[&_[data-slot=progress-indicator]]:bg-primary"
        )}
      />
      {caption && <span className="text-xs text-muted-foreground">{caption}</span>}
    </div>
  );
}

function ServiceRow({ name, ok }: { name: string; ok: boolean | undefined }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{name}</span>
      <span className={cn("flex items-center gap-2 font-semibold", ok === false && "text-critical")}>
        <span className={cn("size-2 rounded-full", ok === undefined ? "bg-muted-foreground" : ok ? "bg-success" : "bg-critical")} />
        {ok === undefined ? "Checking…" : ok ? "Running" : "Failed"}
      </span>
    </div>
  );
}

const ROW_BADGE: Record<CameraRowState, { text: string; cls: string }> = {
  offline: { text: "Offline", cls: "bg-offline-subtle text-offline" },
  not_recording: { text: "Not recording", cls: "bg-critical-subtle text-critical" },
  disabled: { text: "Recording off", cls: "bg-muted text-muted-foreground" },
  ok: { text: "Recording", cls: "bg-success-subtle text-success" },
};

// The dot repeats the badge colour: a green dot beside a red "Not recording" badge read as
// "this camera is fine".
const ROW_DOT: Record<CameraRowState, string> = {
  offline: "bg-offline",
  not_recording: "bg-critical",
  disabled: "bg-muted-foreground",
  ok: "bg-success",
};

/* ------------------------------------------------------------------------- */
/* Page                                                                       */
/* ------------------------------------------------------------------------- */

export const DashboardPage: React.FC = () => {
  const siteZone = useSiteTimeZone();
  const user = useCurrentUser();
  const isManager = user?.role === "owner" || user?.role === "operator";
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const dismissAlert = useUiStore((s) => s.dismissAlert);
  // CPU/memory are diagnostics, not user value (REQUIREMENTS out-of-scope): only in technical view.
  const showTechnical = useUiStore((s) => s.viewMode) === "advanced";

  const { data: health, error: healthError, isLoading: healthLoading, refetch: refetchHealth } = useHealth();
  const { data: storage, error: storageError, isLoading: storageLoading, refetch: refetchStorage } = useStorageStatus();
  const { data: rawAlerts, refetch: refetchAlerts } = useAlerts();
  const { data: rawCameras, isLoading: camerasLoading, refetch: refetchCameras } = useCameras();
  const { data: rawRecList, refetch: refetchRecording } = useRecordingStatus();
  const { data: outages = [] } = useOutages();
  const { data: metrics } = useSystemMetrics();
  const { data: recentEvents } = useUnreadCount();

  const cameras = Array.isArray(rawCameras) ? rawCameras : [];
  const recList = Array.isArray(rawRecList) ? rawRecList : [];
  const [outageDialogOpen, setOutageDialogOpen] = useState(false);

  const openOutageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const o of Array.isArray(outages) ? outages : []) {
      if (o.ended_at === null) map.set(o.camera_serial, o.started_at);
    }
    return map;
  }, [outages]);

  const status = evaluateRecorderStatus({
    health,
    storageState: storage?.health_state,
    cameras,
    recList,
    openOutageSerials: new Set(openOutageMap.keys()),
  });
  const rows = buildCameraRows(cameras, recList, openOutageMap, status.storageBroken);
  const onlineCount = rows.filter((r) => r.online).length;
  const matrixRows = [...rows].sort((a, b) => Number(b.online) - Number(a.online)).slice(0, 4);
  const firstOnline = rows.find((x) => x.online)?.camera.serial ?? rows[0]?.camera.serial;
  const syncPlaybackHref = firstOnline ? `/playback?camera=${encodeURIComponent(firstOnline)}&mode=sync` : "/playback?mode=sync";
  const systemAlerts = (Array.isArray(rawAlerts) ? rawAlerts : []).filter((a) => !dismissedAlertIds.has(a.id));
  const latestEvents = (Array.isArray(recentEvents?.items) ? recentEvents.items : []).slice(0, 6);
  const cameraName = (serial?: string) => cameras.find((c) => c.serial === serial)?.name ?? serial ?? "Camera";
  const hasCritical = systemAlerts.some((a) => a.severity === "critical");

  const total = storage?.telemetry?.total_bytes ?? 0;
  const used = storage?.telemetry?.used_bytes ?? 0;
  const storagePercent = total > 0 ? (used / total) * 100 : null;
  const daysLeft = status.storageBroken ? 0 : (storage?.estimated_retention_days ?? null);

  const isLoading = healthLoading || storageLoading || camerasLoading;
  const refetchAll = () => {
    void refetchHealth();
    void refetchStorage();
    void refetchAlerts();
    void refetchCameras();
    void refetchRecording();
  };

  return (
    <div className="flex min-h-full flex-col gap-4 lg:gap-6">
      <PageIntro description="Keep an eye on recording, check your cameras, and pick up where you left off."
        actions={<><Button variant="outline" asChild><Link to="/search"><Search className="size-4" />Find footage</Link></Button><Button asChild><Link to="/live"><Video className="size-4" />Watch live</Link></Button></>} />
      {/* 1. Is everything recording? */}
      <div
        role="status"
        data-level={status.level}
        className={cn(
          "flex flex-wrap items-center justify-between gap-4 rounded-lg border p-4",
          status.level === "critical" && "border-critical bg-critical-subtle",
          status.level === "warning" && "border-warning bg-warning-subtle",
          status.level === "ok" && "border-success bg-success-subtle"
        )}
      >
        <div className="flex min-w-0 items-center gap-4">
          {status.level === "critical" ? (
            <OctagonAlert className="size-6 shrink-0 text-critical" />
          ) : status.level === "warning" ? (
            <TriangleAlert className="size-6 shrink-0 text-warning" />
          ) : (
            <CircleCheck className="size-6 shrink-0 text-success" />
          )}
          <div className="min-w-0">
            <p
              className={cn(
                "text-xl font-semibold",
                status.level === "critical" && "text-critical",
                status.level === "warning" && "text-warning",
                status.level === "ok" && "text-success"
              )}
            >
              {status.label}
            </p>
            <p className="text-sm text-foreground">{status.storageBroken && storage ? storageSummary(storage) : status.detail}</p>
          </div>
        </div>
        {status.storageBroken && isManager && (
          <Button asChild>
            <Link to="/settings/recording">
              Review storage settings
              <ArrowUpRight className="size-4" />
            </Link>
          </Button>
        )}
      </div>

      {(healthError || storageError) && (
        <InlineError message={DASHBOARD_COPY.LOAD_ERROR_MESSAGE} actionLabel={DASHBOARD_COPY.LOAD_ERROR_ACTION} onAction={refetchAll} />
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <>
          {/* 2. Key numbers */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi
              icon={Cctv}
              label="Cameras online"
              value={`${onlineCount} / ${cameras.length}`}
              hint={
                cameras.length === 0
                  ? "No cameras added yet"
                  : onlineCount < cameras.length
                    ? `${cameras.length - onlineCount} offline`
                    : "All reachable"
              }
              tone={cameras.length === 0 ? "neutral" : onlineCount < cameras.length ? "warning" : "ok"}
            />
            <Kpi
              icon={Disc}
              label="Recording"
              value={`${status.recordingCount} / ${cameras.length}`}
              hint={
                status.storageBroken
                  ? "Storage unavailable"
                  : status.recordingCount < cameras.length
                    ? "Some cameras not saving footage"
                    : cameras.length
                      ? "Saving footage"
                      : undefined
              }
              tone={
                status.storageBroken
                  ? "critical"
                  : cameras.length === 0
                    ? "neutral"
                    : status.recordingCount < cameras.length
                      ? "warning"
                      : "ok"
              }
            />
            <Kpi
              icon={HardDrive}
              label="Footage kept for"
              value={daysLeft == null ? "–" : `${daysLeft} days`}
              hint={storagePercent == null ? "Disk size unknown" : `${Math.round(storagePercent)}% of disk used`}
              tone={status.storageBroken ? "critical" : (storagePercent ?? 0) > 90 ? "warning" : "neutral"}
            />
            <Kpi
              icon={Bell}
              label="Active alerts"
              value={String(systemAlerts.length)}
              hint={hasCritical ? "Includes critical" : systemAlerts.length ? "Needs review" : "All clear"}
              tone={hasCritical ? "critical" : systemAlerts.length ? "warning" : "ok"}
            />
          </div>

          {/* Live Camera Matrix Strip */}
          {matrixRows.length > 0 && (
            <Panel
              icon={LayoutGrid}
              title="Live camera feeds"
              action={
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" asChild>
                    <Link to={syncPlaybackHref}>
                      <Columns2 className="size-4" />
                      Sync playback
                    </Link>
                  </Button>
                  <Button size="sm" asChild>
                    <Link to="/live">
                      <Play className="size-4" />
                      Open multiview
                    </Link>
                  </Button>
                </div>
              }
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {matrixRows.map((row, idx) => {
                  const badge = ROW_BADGE[row.state];
                  return (
                    <div key={row.camera.serial} className="group overflow-hidden rounded-lg border border-border bg-card">
                      <Link
                        to={`/live?camera=${encodeURIComponent(row.camera.serial)}`}
                        className="relative flex aspect-video items-center justify-center overflow-hidden bg-video-bg text-video-fg"
                      >
                        {row.online ? (
                          <img
                            src={`/api/v1/cameras/${encodeURIComponent(row.camera.serial)}/snapshot?profile=low`}
                            alt=""
                            loading="lazy"
                            className="absolute inset-0 size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                            }}
                          />
                        ) : (
                          <Cctv className="size-8 text-video-fg/40" />
                        )}
                        <span className="absolute left-2 top-2 rounded bg-video-overlay/80 px-2 py-1 text-xs font-semibold tabular-nums text-video-fg">
                          CH {String(idx + 1).padStart(2, "0")}
                        </span>
                        <span className={cn("absolute right-2 top-2 rounded-full px-2 py-1 text-xs font-semibold", badge.cls)}>
                          {badge.text}
                        </span>
                      </Link>
                      <div className="flex items-center justify-between gap-2 px-4 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{row.camera.name}</p>
                          <p className="truncate text-xs text-muted-foreground">{row.camera.location || row.camera.serial}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button variant="ghost" size="icon" className="size-8" title="Watch live" aria-label={`Open live view for ${row.camera.name}`} asChild>
                            <Link to={`/live?camera=${encodeURIComponent(row.camera.serial)}`}>
                              <Play className="size-4" />
                            </Link>
                          </Button>
                          <Button variant="ghost" size="icon" className="size-8" title="Play back" aria-label={`Open playback for ${row.camera.name}`} asChild>
                            <Link to={`/playback?camera=${encodeURIComponent(row.camera.serial)}`}>
                              <History className="size-4" />
                            </Link>
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}

          <div className="grid grid-cols-1 gap-4 lg:gap-6 lg:grid-cols-3">
            {/* 3. Cameras, problems first */}
            <Panel
              icon={Video}
              title={`Cameras (${cameras.length})`}
              className="lg:col-span-2 lg:self-start"
              action={
                <div className="flex flex-wrap items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setOutageDialogOpen(true)}>
                    <History className="size-4" />
                    {DASHBOARD_COPY.GLOBAL_OUTAGES}
                  </Button>
                  {isManager && (
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/cameras/add">{DASHBOARD_COPY.CAMERAS_ADD_BUTTON}</Link>
                    </Button>
                  )}
                </div>
              }
            >
              {rows.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
                  <Cctv className="size-8" />
                  {isManager ? "No cameras yet. Add one to start recording." : DASHBOARD_COPY.CAMERAS_EMPTY_VIEWER_DESC}
                </div>
              ) : (
                <ul className="-mx-4 -my-4 divide-y divide-border" aria-label="Camera status">
                  {rows.map((row) => {
                    const badge = ROW_BADGE[row.state];
                    return (
                      <li key={row.camera.serial} data-state={row.state} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-4">
                        <span className={cn("size-2 shrink-0 rounded-full", ROW_DOT[row.state])} aria-hidden />
                        <div className="hidden h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-video-bg sm:flex">
                          {row.online ? (
                            <img
                              src={`/api/v1/cameras/${encodeURIComponent(row.camera.serial)}/snapshot?profile=low`}
                              alt=""
                              loading="lazy"
                              className="size-full object-cover"
                              onError={(e) => {
                                e.currentTarget.style.display = "none";
                              }}
                            />
                          ) : (
                            <Cctv className="size-4 text-video-fg/40" />
                          )}
                        </div>
                        <Link to={`/cameras/${encodeURIComponent(row.camera.serial)}/health`} className="min-w-0 flex-1 basis-40 hover:underline">
                          <span className="block truncate font-semibold">{row.camera.name}</span>
                          <span className="block truncate text-sm text-muted-foreground">{row.problem ?? (row.camera.location || "—")}</span>
                        </Link>
                        <span className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                          <Clock className="size-4 shrink-0" />
                          {row.lastFootage ? `Last footage ${formatRelative(row.lastFootage)}` : "No footage yet"}
                        </span>
                        <span className={cn("rounded-full px-2 py-1 text-xs font-semibold", badge.cls)}>{badge.text}</span>
                        <span className="flex items-center gap-1">
                          <Button variant="ghost" size="sm" asChild>
                            <Link to={`/live?camera=${encodeURIComponent(row.camera.serial)}`} aria-label={`Watch ${row.camera.name} live`}>
                              Live
                            </Link>
                          </Button>
                          <Button variant="ghost" size="sm" asChild>
                            <Link to={`/playback?camera=${encodeURIComponent(row.camera.serial)}`} aria-label={`Play back ${row.camera.name}`}>
                              Playback
                            </Link>
                          </Button>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <div className="flex min-w-0 flex-col gap-4 lg:gap-6">
              {/* 4. What happened recently */}
              <Panel
                icon={Bell}
                title="Recent alerts"
                action={
                  <Button variant="ghost" size="sm" asChild>
                    <Link to="/events">View all alerts</Link>
                  </Button>
                }
              >
                {systemAlerts.length === 0 && latestEvents.length === 0 ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CircleCheck className="size-5 text-success" />
                    No active alerts. All clear.
                  </div>
                ) : (
                  <ul className="flex flex-col gap-2" aria-label="Recent alerts">
                    {systemAlerts.map((a) => (
                      <li
                        key={a.id}
                        className={cn(
                          "flex items-start gap-2 rounded-lg border p-2 text-sm",
                          a.severity === "critical" ? "border-critical bg-critical-subtle" : "border-warning bg-warning-subtle"
                        )}
                      >
                        {a.severity === "critical" ? (
                          <OctagonAlert className="mt-1 size-4 shrink-0 text-critical" />
                        ) : (
                          <TriangleAlert className="mt-1 size-4 shrink-0 text-warning" />
                        )}
                        <span className="min-w-0 flex-1">
                          <span className="block font-semibold">{a.title ?? a.message}</span>
                          {a.title && <span className="block text-muted-foreground">{a.message}</span>}
                          <CameraHealthLink serial={a.camera_serial} source={a.source} className="mt-1" />
                        </span>
                        <Button variant="ghost" size="icon" className="size-8 shrink-0" aria-label="Dismiss alert" title="Dismiss alert" onClick={() => dismissAlert(a.id)}>
                          <X className="size-4" />
                        </Button>
                      </li>
                    ))}
                    {latestEvents.map((evt) => (
                      <li key={evt.id}>
                        <Link
                          to={`/events?camera=${encodeURIComponent(String(evt.camera_serial ?? ""))}`}
                          className="flex items-center gap-2 rounded-lg p-2 text-sm hover:bg-muted"
                        >
                          <Bell className="size-4 shrink-0 text-info" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate font-semibold capitalize">{String(evt.event_type ?? "event").replace(/_/g, " ")}</span>
                            <span className="block truncate text-xs text-muted-foreground">
                              {cameraName(evt.camera_serial)}
                              {evt.start_time ? ` · ${formatDateTime(evt.start_time, siteZone)}` : ""}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel
                icon={HardDrive}
                title="Storage"
                action={
                  <span className={cn("text-xs font-semibold", status.storageBroken ? "text-critical" : "text-success")}>
                    {status.storageBroken ? "Unavailable" : "Storage ready"}
                  </span>
                }
              >
                <Meter
                  label="Disk used"
                  percent={storagePercent}
                  caption={
                    storage?.telemetry
                      ? `${bytesToGiB(used)} of ${bytesToGiB(total)} · ${bytesToGiB(storage.telemetry.free_bytes)} free`
                      : undefined
                  }
                />
                <p className="text-sm text-muted-foreground">
                  {status.storageBroken
                    ? "0 days retention (not saving)"
                    : storage?.estimated_retention_days != null
                      ? `About ${storage.estimated_retention_days} days of footage fit at the current rate.`
                      : "Retention is estimated after some footage is recorded."}
                </p>
              </Panel>

              <Panel
                icon={Server}
                title="System"
                action={<span className="text-xs text-muted-foreground">{metrics ? `Up ${formatUptime(metrics.nvr_uptime_seconds)}` : ""}</span>}
              >
                {showTechnical && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                  <Meter label="CPU" percent={metrics?.cpu_percent ?? null} caption={metrics ? `${metrics.cpu_count} cores` : undefined} />
                  <Meter
                    label="Memory"
                    percent={metrics?.memory_percent ?? null}
                    caption={metrics ? `${bytesToGiB(metrics.memory_used_bytes)} of ${bytesToGiB(metrics.memory_total_bytes)}` : undefined}
                  />
                </div>
                )}
                <div className={cn("flex flex-col gap-2", showTechnical && "border-t border-border pt-4")}>
                  <ServiceRow name="Database" ok={health?.db_ok} />
                  <ServiceRow name="Video service" ok={health?.mediamtx_ok} />
                  <ServiceRow name="Recording storage" ok={health ? !status.storageBroken : undefined} />
                </div>
                {metrics && showTechnical && (
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Cpu className="size-4" />v{metrics.version} · {metrics.platform}
                  </span>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}

      <OutageHistoryDialog
        isOpen={outageDialogOpen}
        onClose={() => setOutageDialogOpen(false)}
        filterCameraSerial={null}
        cameraName={null}
        zone={siteZone}
      />
    </div>
  );
};

export default DashboardPage;
