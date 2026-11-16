import { NativeSelect } from "@/components/ui/native-select";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { GripVertical, Move, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SettingsForm } from "../SettingsForm";
import { useSaveOsd, type CameraSettingsData, type OsdItemPayload } from "../api";
import { CAMERAS_COPY } from "../copy";

export interface OverlaysTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

type Overlay = CameraSettingsData["osd"][number];

const POSITION_NAMES: Record<string, string> = {
  UpperLeft: "Top left",
  UpperRight: "Top right",
  BottomLeft: "Bottom left",
  BottomRight: "Bottom right",
  Custom: "Custom position",
};

const CORNER_COORDS: Record<string, { x: number; y: number }> = {
  UpperLeft: { x: -0.82, y: 0.82 },
  UpperRight: { x: 0.82, y: 0.82 },
  BottomLeft: { x: -0.82, y: -0.82 },
  BottomRight: { x: 0.82, y: -0.82 },
};

function colorHex(color: NonNullable<Overlay["font_color"]>): string {
  return (
    "#" +
    [color.x, color.y, color.z]
      .map((c) => Math.round(c * 255).toString(16).padStart(2, "0"))
      .join("")
  );
}

function colorRgb(color?: Overlay["font_color"] | null): string | undefined {
  if (!color) return undefined;
  const r = Math.round(color.x * 255);
  const g = Math.round(color.y * 255);
  const b = Math.round(color.z * 255);
  return `rgb(${r}, ${g}, ${b})`;
}

function overlayNormalizedCoords(item: Overlay): { x: number; y: number } {
  if (item.position in CORNER_COORDS) {
    return CORNER_COORDS[item.position];
  }
  return {
    x: typeof item.position_x === "number" ? item.position_x : 0,
    y: typeof item.position_y === "number" ? item.position_y : 0,
  };
}

function formatPreviewTimestamp(dateFormat?: string, timeFormat?: string): string {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yyyy = String(now.getFullYear());
  const datePart =
    dateFormat === "yyyy-MM-dd"
      ? `${yyyy}-${mm}-${dd}`
      : dateFormat === "MM/dd/yyyy"
        ? `${mm}/${dd}/${yyyy}`
        : `${dd}/${mm}/${yyyy}`;
  const hours24 = now.getHours();
  const mins = String(now.getMinutes()).padStart(2, "0");
  const secs = String(now.getSeconds()).padStart(2, "0");
  if (timeFormat?.includes("tt")) {
    const ampm = hours24 >= 12 ? "PM" : "AM";
    const h12 = String(hours24 % 12 || 12).padStart(2, "0");
    return `${datePart} ${h12}:${mins}:${secs} ${ampm}`;
  }
  return `${datePart} ${String(hours24).padStart(2, "0")}:${mins}:${secs}`;
}

export function OverlaysTab({ serial, cameraName, settings }: OverlaysTabProps) {
  const timestamp = settings.osd.find((o) => o.osd_type === "DateAndTime");
  const text = settings.osd.find((o) => o.osd_type === "Plain");
  const options = settings.osd_options;
  const [drafts, setDrafts] = useState<Record<string, Overlay>>({});
  const [isDirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draggingToken, setDraggingToken] = useState<string | null>(null);
  const [snapshotTick, setSnapshotTick] = useState(0);
  const canvasRef = useRef<HTMLDivElement>(null);
  const save = useSaveOsd(serial);
  const queryClient = useQueryClient();

  const reset = () => {
    setDrafts(Object.fromEntries(settings.osd.map((o) => [o.token, { ...o }])));
    setDirty(false);
    setError(null);
  };
  useEffect(reset, [settings.osd, serial]);

  const edit = (item: Overlay, key: keyof Overlay, value: unknown) => {
    setDrafts((prev) => ({ ...prev, [item.token]: { ...prev[item.token], [key]: value } }));
    setDirty(true);
  };

  const setCustomCoords = (item: Overlay, nx: number, ny: number) => {
    setDrafts((prev) => ({
      ...prev,
      [item.token]: {
        ...(prev[item.token] || item),
        position: "Custom",
        position_x: nx,
        position_y: ny,
      },
    }));
    setDirty(true);
  };

  const applyPresetCorner = (item: Overlay, pos: string) => {
    const preset = CORNER_COORDS[pos];
    setDrafts((prev) => ({
      ...prev,
      [item.token]: {
        ...(prev[item.token] || item),
        position: pos,
        position_x: preset ? preset.x : (prev[item.token]?.position_x ?? 0),
        position_y: preset ? preset.y : (prev[item.token]?.position_y ?? 0),
      },
    }));
    setDirty(true);
  };

  const base = `/api/v1/cameras/${encodeURIComponent(serial)}/settings/osd`;
  const lifecycle = useMutation({
    mutationFn: async ({ token, type }: { token?: string; type: "Plain" | "DateAndTime" }) =>
      token
        ? apiFetch(`${base}/${encodeURIComponent(token)}`, { method: "DELETE" })
        : apiFetch(base, {
            method: "POST",
            body: {
              osd_type: type,
              position: options?.positions.includes("UpperLeft")
                ? "UpperLeft"
                : options?.positions[0] || "UpperLeft",
              position_x: -0.82,
              position_y: 0.82,
              plain_text: cameraName,
              date_format: options?.date_formats[0] || "dd/MM/yyyy",
              time_format: options?.time_formats[0] || "hh:mm:ss tt",
            },
          }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
    },
  });

  const submit = async () => {
    setError(null);
    try {
      await save.mutateAsync(
        Object.values(drafts).filter(
          (o) => o.osd_type === "Plain" || o.osd_type === "DateAndTime",
        ) as OsdItemPayload[],
      );
      setDirty(false);
      setSnapshotTick((v) => v + 1);
      toast(CAMERAS_COPY.SETTINGS_SAVED);
    } catch (err) {
      setError(err instanceof Error ? err.message : CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  const visibleOverlays = settings.osd.filter(
    (o) => o.osd_type === "Plain" || o.osd_type === "DateAndTime",
  );

  const handlePointerMove = (item: Overlay, e: ReactPointerEvent<HTMLDivElement>) => {
    if (draggingToken !== item.token || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const relX = Math.max(0.04, Math.min(0.96, (e.clientX - rect.left) / rect.width));
    const relY = Math.max(0.06, Math.min(0.94, (e.clientY - rect.top) / rect.height));
    const nx = Number((relX * 2 - 1).toFixed(2));
    const ny = Number((1 - relY * 2).toFixed(2));
    setCustomCoords(item, nx, ny);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">On-screen text</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Drag date/time stamps or title watermarks directly on the camera preview, or pick a preset corner.
        </p>
      </div>

      <SettingsForm
        isDirty={isDirty}
        isSubmitting={save.isPending}
        errorMessage={error}
        onDiscard={reset}
        onSubmit={submit}
        retryLabel={CAMERAS_COPY.RETRY_SAVE}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={lifecycle.isPending || save.isPending}
              onClick={() => lifecycle.mutate({ token: timestamp?.token, type: "DateAndTime" })}
            >
              {timestamp ? "Remove timestamp overlay" : "Enable timestamp overlay"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={lifecycle.isPending || save.isPending}
              onClick={() => lifecycle.mutate({ token: text?.token, type: "Plain" })}
            >
              {text ? "Remove text overlay" : "Enable text overlay"}
            </Button>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-xs"
            onClick={() => setSnapshotTick((v) => v + 1)}
          >
            <RefreshCw className="size-4" />
            Refresh preview
          </Button>
        </div>

        {lifecycle.error && (
          <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-sm text-critical">
            {lifecycle.error.message}
          </p>
        )}

        {visibleOverlays.length > 0 && (
          <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Move className="size-4 text-primary" />
                <h3 className="text-sm font-semibold">Interactive OSD placement</h3>
              </div>
              <span className="text-xs text-muted-foreground">
                Drag overlays anywhere on the frame, then save changes
              </span>
            </div>

            <div
              ref={canvasRef}
              className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-video-bg select-none touch-none"
              aria-label="OSD drag and drop canvas"
            >
              <img
                src={`/api/v1/cameras/${encodeURIComponent(serial)}/snapshot?profile=medium&osd=0&v=${snapshotTick}`}
                alt={`Camera background preview for ${cameraName}`}
                className="pointer-events-none h-full w-full object-cover select-none"
                draggable={false}
              />

              {visibleOverlays.map((original) => {
                const item = drafts[original.token] || original;
                const isTime = item.osd_type === "DateAndTime";
                const coords = overlayNormalizedCoords(item);
                const leftPct = Math.max(8, Math.min(92, ((coords.x + 1) / 2) * 100));
                const topPct = Math.max(10, Math.min(90, ((1 - coords.y) / 2) * 100));
                const label = isTime
                  ? formatPreviewTimestamp(item.date_format, item.time_format)
                  : item.plain_text || cameraName;
                const active = draggingToken === item.token;
                const fontRgb = colorRgb(item.font_color);

                return (
                  <div
                    key={item.token}
                    role="button"
                    tabIndex={0}
                    aria-label={isTime ? "Drag timestamp overlay" : "Drag text overlay"}
                    onPointerDown={(e) => {
                      e.currentTarget.setPointerCapture(e.pointerId);
                      setDraggingToken(item.token);
                    }}
                    onPointerMove={(e) => handlePointerMove(item, e)}
                    onPointerUp={(e) => {
                      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
                        e.currentTarget.releasePointerCapture(e.pointerId);
                      }
                      setDraggingToken(null);
                    }}
                    onPointerCancel={() => setDraggingToken(null)}
                    className={`absolute flex cursor-grab items-center gap-1 rounded-md border px-2 py-1 font-mono text-xs font-semibold shadow-sm active:cursor-grabbing ${
                      active
                        ? "border-primary bg-selected/90 ring-2 ring-primary"
                        : "border-border/70 bg-background/75 hover:border-primary"
                    }`}
                    // dynamic-style: live OSD drag coordinates and user font color
                    style={{
                      left: `${leftPct}%`,
                      top: `${topPct}%`,
                      transform: "translate(-50%, -50%)",
                      color: fontRgb,
                    }}
                  >
                    <GripVertical className="size-3 shrink-0 text-primary" />
                    <span className="whitespace-nowrap">{label}</span>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
              {visibleOverlays.map((original) => {
                const item = drafts[original.token] || original;
                const isTime = item.osd_type === "DateAndTime";
                const coords = overlayNormalizedCoords(item);
                return (
                  <span key={item.token}>
                    {isTime ? "Timestamp" : "Text"}:{" "}
                    <span className="font-mono text-foreground">
                      {POSITION_NAMES[item.position] || item.position} ({coords.x.toFixed(2)},{" "}
                      {coords.y.toFixed(2)})
                    </span>
                  </span>
                );
              })}
            </div>
          </section>
        )}

        {!settings.osd.length && (
          <p className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
            No text overlays are enabled on this camera. Enable a timestamp or text overlay to configure it.
          </p>
        )}

        {visibleOverlays.map((original) => {
          const item = drafts[original.token] || original;
          const isTime = item.osd_type === "DateAndTime";
          const positions = [...new Set([...(options?.positions || []), item.position])];
          const formats = (
            key: "date_format" | "time_format",
            title: string,
            choices: string[],
          ) => (
            <label className="vms-field">
              {title}
              <NativeSelect
                aria-label={title}
                value={item[key]}
                onChange={(e) => edit(item, key, e.target.value)}
              >
                {[...new Set([...choices, item[key]])].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </NativeSelect>
            </label>
          );

          return (
            <section
              key={item.token}
              className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">{isTime ? "Date & timestamp" : "Text overlay"}</h3>
                <div className="flex flex-wrap gap-1">
                  {(["UpperLeft", "UpperRight", "BottomLeft", "BottomRight"] as const).map(
                    (corner) => (
                      <Button
                        key={corner}
                        type="button"
                        size="sm"
                        variant={item.position === corner ? "secondary" : "outline"}
                        className="text-xs"
                        onClick={() => applyPresetCorner(item, corner)}
                      >
                        {POSITION_NAMES[corner]}
                      </Button>
                    ),
                  )}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                {!isTime && (
                  <label className="vms-field sm:col-span-2">
                    Custom Title / Watermark
                    <Input
                      aria-label="Custom Title / Watermark"
                      value={item.plain_text || ""}
                      maxLength={256}
                      onChange={(e) => edit(item, "plain_text", e.target.value)}
                    />
                  </label>
                )}

                <label className="vms-field">
                  {isTime ? "Date & Timestamp Position" : "Title Overlay Position"}
                  <NativeSelect
                    aria-label={isTime ? "Date & Timestamp Position" : "Title Overlay Position"}
                    value={item.position}
                    onChange={(e) => applyPresetCorner(item, e.target.value)}
                  >
                    {positions.map((p) => (
                      <option key={p} value={p}>
                        {POSITION_NAMES[p] || p}
                      </option>
                    ))}
                  </NativeSelect>
                </label>

                {item.position === "Custom" &&
                  (["position_x", "position_y"] as const).map((key) => (
                    <label key={key} className="vms-field">
                      {isTime ? "Timestamp" : "Text"}{" "}
                      {key === "position_x" ? "horizontal" : "vertical"} position (−1 to 1)
                      <Input
                        type="number"
                        min={-1}
                        max={1}
                        step="0.01"
                        value={item[key] ?? 0}
                        onChange={(e) => edit(item, key, Number(e.target.value))}
                      />
                    </label>
                  ))}

                {isTime && formats("date_format", "Date format", options?.date_formats || [])}
                {isTime && formats("time_format", "Time format", options?.time_formats || [])}

                {options?.font_size_range && (
                  <label className="vms-field">
                    Font size
                    <Input
                      type="number"
                      min={options.font_size_range[0]}
                      max={options.font_size_range[1]}
                      value={item.font_size ?? ""}
                      onChange={(e) =>
                        edit(item, "font_size", e.target.value ? Number(e.target.value) : null)
                      }
                    />
                  </label>
                )}

                {options?.font_color_range &&
                  item.font_color &&
                  item.font_color.colorspace.endsWith("/RGB") && (
                    <label className="vms-field">
                      Font color
                      <Input
                        type="color"
                        aria-label={isTime ? "Timestamp font color" : "Text font color"}
                        value={colorHex(item.font_color)}
                        onChange={(e) => {
                          const value = e.target.value.slice(1);
                          edit(item, "font_color", {
                            ...item.font_color,
                            x: parseInt(value.slice(0, 2), 16) / 255,
                            y: parseInt(value.slice(2, 4), 16) / 255,
                            z: parseInt(value.slice(4, 6), 16) / 255,
                          });
                        }}
                      />
                    </label>
                  )}
              </div>
            </section>
          );
        })}

        {!options && (
          <p className="text-xs text-muted-foreground">
            Overlay option lists were not reported. Existing positions and formats are preserved.
          </p>
        )}
      </SettingsForm>
    </div>
  );
}
