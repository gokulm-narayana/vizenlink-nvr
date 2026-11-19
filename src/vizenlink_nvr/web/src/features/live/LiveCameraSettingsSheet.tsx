import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowUpRight,
  Check,
  Loader2,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InlineError } from "@/components/InlineError";
import {
  useCameraSettings,
  useSaveImaging,
  useSaveOsd,
  type CameraSettingsData,
  type ImagingPayload,
  type OsdItemPayload,
} from "@/features/cameras/api";
import { availableNightVisionTypes, isWdrVisible } from "@/features/cameras/capabilities";
import { CAMERAS_COPY } from "@/features/cameras/copy";

export interface LiveCameraSettingsSheetProps {
  serial: string | null;
  cameraName: string;
  channel?: number;
  onClose: () => void;
}

type SheetTab = "image" | "overlays";
type Overlay = CameraSettingsData["osd"][number];

interface ImageFormState {
  brightness: number;
  contrast: number;
  saturation: number;
  sharpness: number;
  irCutFilter: string;
  wdrMode: string;
  wdrLevel: number;
  nightVisionType: string;
  mirrorFlip: string;
  antiFlicker: string;
  exposureMode: string;
  exposureTime: number;
  exposureGain: number;
  whiteBalanceMode: string;
}

const SCENE_PRESETS: Array<{
  label: string;
  brightness: number;
  contrast: number;
  saturation: number;
  sharpness: number;
}> = [
  { label: "Standard", brightness: 50, contrast: 50, saturation: 50, sharpness: 50 },
  { label: "Vivid", brightness: 52, contrast: 60, saturation: 68, sharpness: 58 },
  { label: "Low Light", brightness: 65, contrast: 55, saturation: 45, sharpness: 45 },
  { label: "Crisp", brightness: 50, contrast: 58, saturation: 50, sharpness: 72 },
];

const POSITION_NAMES: Record<string, string> = {
  UpperLeft: "Top left",
  UpperRight: "Top right",
  BottomLeft: "Bottom left",
  LowerLeft: "Bottom left",
  BottomRight: "Bottom right",
  LowerRight: "Bottom right",
  Custom: "Custom",
};

const CORNER_COORDS: Record<string, { x: number; y: number }> = {
  UpperLeft: { x: -0.82, y: 0.82 },
  UpperRight: { x: 0.82, y: 0.82 },
  BottomLeft: { x: -0.82, y: -0.82 },
  LowerLeft: { x: -0.82, y: -0.82 },
  BottomRight: { x: 0.82, y: -0.82 },
  LowerRight: { x: 0.82, y: -0.82 },
};

const DEFAULT_FONT_COLOR: NonNullable<Overlay["font_color"]> = {
  x: 1,
  y: 1,
  z: 1,
  colorspace: "http://www.onvif.org/ver10/colorspace/RGB",
};

function colorHex(color: NonNullable<Overlay["font_color"]>): string {
  return (
    "#" +
    [color.x, color.y, color.z]
      .map((c) => Math.round(c * 255).toString(16).padStart(2, "0"))
      .join("")
  );
}

function clampToRange(value: number, range?: [number, number]): number {
  if (!range) return value;
  return Math.max(range[0], Math.min(range[1], value));
}

function formFromCurrent(current: CameraSettingsData["imaging"]["current"]): ImageFormState {
  return {
    brightness: current.brightness,
    contrast: current.contrast,
    saturation: current.color_saturation,
    sharpness: current.sharpness,
    irCutFilter: current.ir_cut_filter,
    wdrMode: current.wdr_mode,
    wdrLevel: current.wdr_level,
    nightVisionType: current.night_vision_type,
    mirrorFlip: current.mirror_flip,
    antiFlicker: current.anti_flicker,
    exposureMode: current.exposure_mode ?? "",
    exposureTime: current.exposure_time ?? 0,
    exposureGain: current.exposure_gain ?? 0,
    whiteBalanceMode: current.white_balance_mode ?? "",
  };
}

function buildImagingPayload(
  form: ImageFormState,
  options: CameraSettingsData["imaging"]["options"],
): ImagingPayload {
  const irCutModes = options.ir_cut_filter_modes ?? [];
  const wdrSupported = isWdrVisible(options);
  const exposureModes = options.exposure_modes ?? [];
  const whiteBalanceModes = options.white_balance_modes ?? [];
  const isManualExposure = form.exposureMode.toUpperCase() === "MANUAL";

  return {
    brightness: Number(form.brightness),
    contrast: Number(form.contrast),
    color_saturation: Number(form.saturation),
    sharpness: Number(form.sharpness),
    ...(irCutModes.length ? { ir_cut_filter: form.irCutFilter } : {}),
    ...(wdrSupported ? { wdr_mode: form.wdrMode, wdr_level: Number(form.wdrLevel) } : {}),
    night_vision_type: form.nightVisionType,
    mirror_flip: form.mirrorFlip,
    anti_flicker: form.antiFlicker,
    ...(exposureModes.length && form.exposureMode ? { exposure_mode: form.exposureMode } : {}),
    ...(isManualExposure && options.exposure_time_range
      ? { exposure_time: Number(form.exposureTime) }
      : {}),
    ...(isManualExposure && options.exposure_gain_range
      ? { exposure_gain: Number(form.exposureGain) }
      : {}),
    ...(whiteBalanceModes.length && form.whiteBalanceMode
      ? { white_balance_mode: form.whiteBalanceMode }
      : {}),
  };
}

function formsEqual(a: ImageFormState, b: ImageFormState): boolean {
  return (
    a.brightness === b.brightness &&
    a.contrast === b.contrast &&
    a.saturation === b.saturation &&
    a.sharpness === b.sharpness &&
    a.irCutFilter === b.irCutFilter &&
    a.wdrMode === b.wdrMode &&
    a.wdrLevel === b.wdrLevel &&
    a.nightVisionType === b.nightVisionType &&
    a.mirrorFlip === b.mirrorFlip &&
    a.antiFlicker === b.antiFlicker &&
    a.exposureMode === b.exposureMode &&
    a.exposureTime === b.exposureTime &&
    a.exposureGain === b.exposureGain &&
    a.whiteBalanceMode === b.whiteBalanceMode
  );
}

interface SheetBodyProps {
  serial: string;
  cameraName: string;
  channel?: number;
  onClose: () => void;
}

const LiveCameraSettingsSheetBody: React.FC<SheetBodyProps> = ({
  serial,
  cameraName,
  channel,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<SheetTab>("image");
  const [autoApply, setAutoApply] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justApplied, setJustApplied] = useState(false);

  const queryClient = useQueryClient();
  const settingsQuery = useCameraSettings(serial, true);
  const settings = settingsQuery.data;
  const saveImaging = useSaveImaging(serial);
  const saveOsd = useSaveOsd(serial);

  const [form, setForm] = useState<ImageFormState | null>(null);
  const baselineRef = useRef<{ serial: string; form: ImageFormState } | null>(null);
  const isDirtyRef = useRef(false);
  const [isDirty, setIsDirty] = useState(false);
  const debounceTimerRef = useRef<number | null>(null);

  const [osdDrafts, setOsdDrafts] = useState<Record<string, Overlay>>({});
  const [osdDirty, setOsdDirty] = useState(false);
  const [osdError, setOsdError] = useState<string | null>(null);

  const clearDebounce = () => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  };

  useEffect(() => {
    clearDebounce();
    baselineRef.current = null;
    isDirtyRef.current = false;
    setForm(null);
    setIsDirty(false);
    setSaveError(null);
    setJustApplied(false);
    setOsdDrafts({});
    setOsdDirty(false);
    setOsdError(null);
    return () => clearDebounce();
  }, [serial]);

  useEffect(() => {
    const current = settings?.imaging?.current;
    if (!current) return;
    const mapped = formFromCurrent(current);
    if (!baselineRef.current || baselineRef.current.serial !== serial) {
      baselineRef.current = { serial, form: mapped };
      setForm(mapped);
      isDirtyRef.current = false;
      setIsDirty(false);
    } else if (!isDirtyRef.current) {
      setForm(mapped);
    }
  }, [settings?.imaging?.current, serial]);

  useEffect(() => {
    if (!settings?.osd) return;
    setOsdDrafts(Object.fromEntries(settings.osd.map((o) => [o.token, { ...o }])));
    setOsdDirty(false);
    setOsdError(null);
  }, [settings?.osd, serial]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onClose]);

  const applyImaging = async (nextForm: ImageFormState, announce = false) => {
    const options = settings?.imaging?.options;
    if (!options) return;
    clearDebounce();
    setSaveError(null);
    try {
      await saveImaging.mutateAsync(buildImagingPayload(nextForm, options));
      isDirtyRef.current = false;
      setIsDirty(false);
      setJustApplied(true);
      if (announce) {
        toast.success(CAMERAS_COPY.SETTINGS_SAVED);
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  const scheduleApply = (nextForm: ImageFormState) => {
    clearDebounce();
    if (!autoApply) return;
    debounceTimerRef.current = window.setTimeout(() => {
      void applyImaging(nextForm, false);
    }, 450);
  };

  const updateImageField = <K extends keyof ImageFormState>(field: K, value: ImageFormState[K]) => {
    setForm((prev) => {
      if (!prev) return prev;
      const next = { ...prev, [field]: value };
      isDirtyRef.current = true;
      setIsDirty(true);
      setJustApplied(false);
      scheduleApply(next);
      return next;
    });
  };

  const applyPreset = (preset: (typeof SCENE_PRESETS)[number]) => {
    const options = settings?.imaging?.options;
    if (!form || !options) return;
    const next: ImageFormState = {
      ...form,
      brightness: clampToRange(preset.brightness, options.brightness_range),
      contrast: clampToRange(preset.contrast, options.contrast_range),
      saturation: clampToRange(preset.saturation, options.color_saturation_range),
      sharpness: clampToRange(preset.sharpness, options.sharpness_range),
    };
    setForm(next);
    isDirtyRef.current = true;
    setIsDirty(true);
    setJustApplied(false);
    if (autoApply) {
      void applyImaging(next, false);
    }
  };

  const handleRevert = async () => {
    const baseline = baselineRef.current?.form;
    if (!baseline) return;
    setForm(baseline);
    await applyImaging(baseline, false);
    toast.success(`Reverted ${cameraName} image settings`);
  };

  const osdBaseUrl = `/api/v1/cameras/${encodeURIComponent(serial)}/settings/osd`;
  const osdLifecycle = useMutation({
    mutationFn: async ({ token, type }: { token?: string; type: "Plain" | "DateAndTime" }) => {
      const options = settings?.osd_options;
      return token
        ? apiFetch(`${osdBaseUrl}/${encodeURIComponent(token)}`, { method: "DELETE" })
        : apiFetch(osdBaseUrl, {
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
              font_color: DEFAULT_FONT_COLOR,
            },
          });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
    },
  });

  const handleEditOsd = (item: Overlay, key: keyof Overlay, value: unknown) => {
    setOsdDrafts((prev) => ({
      ...prev,
      [item.token]: { ...(prev[item.token] || item), [key]: value },
    }));
    setOsdDirty(true);
  };

  const applyOsdCorner = (item: Overlay, pos: string) => {
    const preset = CORNER_COORDS[pos];
    setOsdDrafts((prev) => ({
      ...prev,
      [item.token]: {
        ...(prev[item.token] || item),
        position: pos,
        position_x: preset ? preset.x : (prev[item.token]?.position_x ?? 0),
        position_y: preset ? preset.y : (prev[item.token]?.position_y ?? 0),
      },
    }));
    setOsdDirty(true);
  };

  const handleSaveOsd = async () => {
    setOsdError(null);
    try {
      const payloads = Object.values(osdDrafts).filter(
        (o) => o.osd_type === "Plain" || o.osd_type === "DateAndTime",
      ) as OsdItemPayload[];
      await saveOsd.mutateAsync(payloads);
      setOsdDirty(false);
      toast.success(CAMERAS_COPY.SETTINGS_SAVED);
    } catch (err) {
      setOsdError(err instanceof Error ? err.message : CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  const options = settings?.imaging?.options;
  const irCutModes = options?.ir_cut_filter_modes ?? [];
  const nightVisionChoices = availableNightVisionTypes(options);
  const wdrSupported = isWdrVisible(options);
  const dayNightNow = settings?.imaging?.current?.day_night_now ?? null;

  const hasChangesFromBaseline = Boolean(
    form && baselineRef.current && !formsEqual(form, baselineRef.current.form),
  );
  const showChangedBadge = isDirty || hasChangesFromBaseline;

  const timestampOsd = settings?.osd?.find((o) => o.osd_type === "DateAndTime");
  const textOsd = settings?.osd?.find((o) => o.osd_type === "Plain");
  const visibleOsds = (settings?.osd ?? []).filter(
    (o) => o.osd_type === "Plain" || o.osd_type === "DateAndTime",
  );
  const osdOptions = settings?.osd_options;

  return (
    <div
      role="dialog"
      aria-label={`${cameraName} live settings`}
      data-video-chrome
      className="fixed top-4 right-4 bottom-4 z-50 flex w-[calc(100vw-2rem)] sm:w-full max-w-md flex-col overflow-hidden rounded-xl border border-border bg-card/95 text-foreground shadow-lg backdrop-blur-sm"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0 flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 shrink-0 text-primary" />
            <h2 className="truncate text-sm font-semibold">
              {channel ? `CH ${channel} · ` : ""}
              {cameraName}
            </h2>
            {showChangedBadge && (
              <Badge variant="secondary" className="text-xs font-semibold">
                Changed
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Adjust settings while watching the live feed</span>
            {saveImaging.isPending && (
              <span className="inline-flex items-center gap-1 text-primary">
                <Loader2 className="size-3 animate-spin" />
                Applying
              </span>
            )}
            {!saveImaging.isPending && justApplied && (
              <span className="inline-flex items-center gap-1 text-success">
                <Check className="size-3" />
                Applied
              </span>
            )}
          </div>
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Close live settings"
          onClick={onClose}
          className="size-8 shrink-0"
        >
          <X className="size-4" />
        </Button>
      </div>

      {/* Tabs + Live preview switch */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as SheetTab)}>
          <TabsList>
            <TabsTrigger value="image" className="text-xs font-semibold">
              Image
            </TabsTrigger>
            <TabsTrigger value="overlays" className="text-xs font-semibold">
              Overlays
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {activeTab === "image" && (
          <label className="flex items-center gap-2 text-xs font-normal text-muted-foreground cursor-pointer">
            <span>Live preview</span>
            <Switch
              aria-label="Auto-apply live preview"
              checked={autoApply}
              onCheckedChange={setAutoApply}
            />
          </label>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {settingsQuery.isLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : settingsQuery.error ? (
          <InlineError
            title="Live settings unavailable"
            message={settingsQuery.error.message}
            actionLabel="Reload settings"
            onAction={() => void settingsQuery.refetch()}
            pending={settingsQuery.isFetching}
          />
        ) : settings?.unavailable_sections?.includes(activeTab) ? (
          <InlineError
            message={settings.read_errors?.[activeTab] || "Camera values could not be read."}
            actionLabel="Reload settings"
            onAction={() => void settingsQuery.refetch()}
            pending={settingsQuery.isFetching}
          />
        ) : activeTab === "image" ? (
          !form || !options ? (
            <p className="text-xs text-muted-foreground">
              No imaging options reported by this camera.
            </p>
          ) : (
            <>
              {saveError && (
                <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-xs text-critical">
                  {saveError}
                </p>
              )}

              {/* Scene Presets */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 text-xs font-semibold text-foreground">
                  <Sparkles className="size-3.5 text-primary" />
                  <span>Quick presets</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {SCENE_PRESETS.map((preset) => (
                    <Button
                      key={preset.label}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="text-xs font-semibold"
                      onClick={() => applyPreset(preset)}
                    >
                      {preset.label}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Day / Night & Night Vision */}
              <div className="flex flex-col gap-4 rounded-lg border border-border bg-background/60 p-4">
                {irCutModes.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground">Day / night mode</span>
                      {dayNightNow && (
                        <span className="text-xs text-muted-foreground">
                          Now: {dayNightNow === "day" ? "Day" : "Night"}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2" role="group" aria-label="Day or night mode">
                      {irCutModes.map((mode) => {
                        const upper = mode.toUpperCase();
                        const active = form.irCutFilter.toUpperCase() === upper;
                        const label =
                          upper === "AUTO"
                            ? "Auto"
                            : upper === "ON"
                              ? "Day (Colour)"
                              : upper === "OFF"
                                ? "Night (IR)"
                                : mode;
                        return (
                          <Button
                            key={mode}
                            type="button"
                            size="sm"
                            variant={active ? "default" : "outline"}
                            aria-pressed={active}
                            className="text-xs"
                            onClick={() => updateImageField("irCutFilter", mode)}
                          >
                            {label}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                  <span>Night vision mode</span>
                  <NativeSelect
                    aria-label="Night Vision Mode"
                    value={form.nightVisionType}
                    onChange={(e) => updateImageField("nightVisionType", e.target.value)}
                  >
                    {nightVisionChoices.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice === "grey"
                          ? "Infrared (Black & White)"
                          : choice === "color"
                            ? "Full Color Night Vision"
                            : "Smart Dual-Mode (Color on Motion)"}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
              </div>

              {/* Picture Sliders */}
              <div className="flex flex-col gap-4 rounded-lg border border-border bg-background/60 p-4">
                {(
                  [
                    {
                      id: "live-img-brightness",
                      label: "Brightness",
                      field: "brightness" as const,
                      range: options.brightness_range,
                    },
                    {
                      id: "live-img-contrast",
                      label: "Contrast",
                      field: "contrast" as const,
                      range: options.contrast_range,
                    },
                    {
                      id: "live-img-saturation",
                      label: "Color Saturation",
                      field: "saturation" as const,
                      range: options.color_saturation_range,
                    },
                    {
                      id: "live-img-sharpness",
                      label: "Sharpness",
                      field: "sharpness" as const,
                      range: options.sharpness_range,
                    },
                  ] as const
                ).map((slider) => (
                  <div key={slider.field} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <label
                        htmlFor={slider.id}
                        className="text-xs font-semibold text-foreground"
                      >
                        {slider.label}
                      </label>
                      <span className="text-xs font-mono tabular-nums text-muted-foreground">
                        {form[slider.field]}
                      </span>
                    </div>
                    <input
                      id={slider.id}
                      type="range"
                      min={slider.range?.[0] ?? 0}
                      max={slider.range?.[1] ?? 100}
                      value={form[slider.field]}
                      onChange={(e) => updateImageField(slider.field, Number(e.target.value))}
                      className="h-2 w-full cursor-pointer accent-primary"
                    />
                  </div>
                ))}
              </div>

              {/* WDR */}
              {wdrSupported && (
                <div className="flex flex-col gap-4 rounded-lg border border-border bg-background/60 p-4">
                  <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                    <span>WDR Mode</span>
                    <NativeSelect
                      aria-label="WDR Mode"
                      value={form.wdrMode}
                      onChange={(e) => updateImageField("wdrMode", e.target.value)}
                    >
                      <option value="OFF">Off</option>
                      <option value="ON">On</option>
                      <option value="AUTO">Auto</option>
                    </NativeSelect>
                  </label>
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <label htmlFor="live-img-wdr" className="text-xs font-semibold text-foreground">
                        WDR Strength Level
                      </label>
                      <span className="text-xs font-mono tabular-nums text-muted-foreground">
                        {form.wdrLevel}
                      </span>
                    </div>
                    <input
                      id="live-img-wdr"
                      type="range"
                      min={options.wdr_level_range?.[0] ?? 0}
                      max={options.wdr_level_range?.[1] ?? 100}
                      value={form.wdrLevel}
                      onChange={(e) => updateImageField("wdrLevel", Number(e.target.value))}
                      className="h-2 w-full cursor-pointer accent-primary"
                    />
                  </div>
                </div>
              )}

              {/* Orientation & Anti-Flicker */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-lg border border-border bg-background/60 p-4">
                <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                  <span>Orientation</span>
                  <NativeSelect
                    aria-label="Orientation"
                    value={form.mirrorFlip}
                    onChange={(e) => updateImageField("mirrorFlip", e.target.value)}
                  >
                    <option value="off">Normal</option>
                    <option value="flip">Flip (Vertical)</option>
                    <option value="mirror">Mirror (Horizontal)</option>
                    <option value="flip_mirror">Flip &amp; Mirror (180°)</option>
                  </NativeSelect>
                </label>

                <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                  <span>Anti-Flicker</span>
                  <NativeSelect
                    aria-label="Anti-Flicker Frequency"
                    value={form.antiFlicker}
                    onChange={(e) => updateImageField("antiFlicker", e.target.value)}
                  >
                    <option value="Auto">Auto</option>
                    <option value="50Hz">50 Hz</option>
                    <option value="60Hz">60 Hz</option>
                    <option value="Off">Off</option>
                  </NativeSelect>
                </label>
              </div>
            </>
          )
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={osdLifecycle.isPending || saveOsd.isPending}
                onClick={() =>
                  osdLifecycle.mutate({ token: timestampOsd?.token, type: "DateAndTime" })
                }
                className="text-xs"
              >
                {timestampOsd ? "Remove timestamp overlay" : "Enable timestamp overlay"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={osdLifecycle.isPending || saveOsd.isPending}
                onClick={() => osdLifecycle.mutate({ token: textOsd?.token, type: "Plain" })}
                className="text-xs"
              >
                {textOsd ? "Remove text overlay" : "Enable text overlay"}
              </Button>
            </div>

            {(osdLifecycle.error || osdError) && (
              <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-xs text-critical">
                {osdError || osdLifecycle.error?.message}
              </p>
            )}

            {visibleOsds.length === 0 ? (
              <p className="rounded-lg border border-border bg-background/60 p-4 text-xs text-muted-foreground">
                No text overlays enabled on this camera.
              </p>
            ) : (
              visibleOsds.map((orig) => {
                const item = osdDrafts[orig.token] || orig;
                const isTime = item.osd_type === "DateAndTime";
                const posList = osdOptions?.positions || [];
                const bottomLeft =
                  posList.includes("LowerLeft") && !posList.includes("BottomLeft")
                    ? "LowerLeft"
                    : "BottomLeft";
                const bottomRight =
                  posList.includes("LowerRight") && !posList.includes("BottomRight")
                    ? "LowerRight"
                    : "BottomRight";
                const currentColor = item.font_color ?? DEFAULT_FONT_COLOR;
                const supportsRgbColor =
                  Boolean(osdOptions?.font_color_range || item.font_color) &&
                  (!item.font_color?.colorspace || item.font_color.colorspace.endsWith("/RGB"));

                const isCornerActive = (corner: string) => {
                  if (item.position === corner) return true;
                  if (corner === "LowerLeft" || corner === "BottomLeft") {
                    return item.position === "LowerLeft" || item.position === "BottomLeft";
                  }
                  if (corner === "LowerRight" || corner === "BottomRight") {
                    return item.position === "LowerRight" || item.position === "BottomRight";
                  }
                  return false;
                };

                return (
                  <div
                    key={item.token}
                    className="flex flex-col gap-4 rounded-lg border border-border bg-background/60 p-4"
                  >
                    <div className="text-xs font-semibold text-foreground">
                      {isTime ? "Date & timestamp" : "Text overlay"}
                    </div>

                    {!isTime && (
                      <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                        <span>Custom Title / Watermark</span>
                        <Input
                          aria-label="Custom Title / Watermark"
                          value={item.plain_text || ""}
                          maxLength={256}
                          onChange={(e) => handleEditOsd(item, "plain_text", e.target.value)}
                        />
                      </label>
                    )}

                    <div className="flex flex-wrap gap-1">
                      {(["UpperLeft", "UpperRight", bottomLeft, bottomRight] as const).map(
                        (corner) => (
                          <Button
                            key={corner}
                            type="button"
                            size="sm"
                            variant={isCornerActive(corner) ? "secondary" : "outline"}
                            className="text-xs"
                            onClick={() => applyOsdCorner(item, corner)}
                          >
                            {POSITION_NAMES[corner]}
                          </Button>
                        ),
                      )}
                    </div>

                    {isTime && (
                      <div className="grid grid-cols-2 gap-2">
                        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                          <span>Date format</span>
                          <NativeSelect
                            aria-label="Date format"
                            value={item.date_format}
                            onChange={(e) => handleEditOsd(item, "date_format", e.target.value)}
                          >
                            {[
                              ...new Set([...(osdOptions?.date_formats || []), item.date_format]),
                            ].map((fmt) => (
                              <option key={fmt} value={fmt}>
                                {fmt}
                              </option>
                            ))}
                          </NativeSelect>
                        </label>
                        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                          <span>Time format</span>
                          <NativeSelect
                            aria-label="Time format"
                            value={item.time_format}
                            onChange={(e) => handleEditOsd(item, "time_format", e.target.value)}
                          >
                            {[
                              ...new Set([...(osdOptions?.time_formats || []), item.time_format]),
                            ].map((fmt) => (
                              <option key={fmt} value={fmt}>
                                {fmt}
                              </option>
                            ))}
                          </NativeSelect>
                        </label>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2">
                      {osdOptions?.font_size_range && (
                        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                          <span>Font size</span>
                          <Input
                            type="number"
                            min={osdOptions.font_size_range[0]}
                            max={osdOptions.font_size_range[1]}
                            value={item.font_size ?? ""}
                            onChange={(e) =>
                              handleEditOsd(
                                item,
                                "font_size",
                                e.target.value ? Number(e.target.value) : null,
                              )
                            }
                          />
                        </label>
                      )}

                      {supportsRgbColor && (
                        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground">
                          <span>Font color</span>
                          <Input
                            type="color"
                            aria-label={isTime ? "Timestamp font color" : "Text font color"}
                            value={colorHex(currentColor)}
                            onChange={(e) => {
                              const hex = e.target.value.slice(1);
                              handleEditOsd(item, "font_color", {
                                ...currentColor,
                                x: parseInt(hex.slice(0, 2), 16) / 255,
                                y: parseInt(hex.slice(2, 4), 16) / 255,
                                z: parseInt(hex.slice(4, 6), 16) / 255,
                              });
                            }}
                          />
                        </label>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border p-4 bg-card">
        <Button variant="ghost" size="sm" asChild className="text-xs">
          <Link to={`/cameras/${encodeURIComponent(serial)}?tab=${activeTab}`}>
            <span>Open full settings</span>
            <ArrowUpRight className="size-3.5" />
          </Link>
        </Button>

        {activeTab === "image" ? (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!hasChangesFromBaseline || saveImaging.isPending}
              onClick={() => void handleRevert()}
              className="text-xs"
            >
              <RotateCcw className="size-3.5" />
              Revert
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!form || !options || saveImaging.isPending}
              onClick={() => form && void applyImaging(form, true)}
              className="text-xs"
            >
              {saveImaging.isPending && <Loader2 className="size-3.5 animate-spin" />}
              Apply image settings
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            size="sm"
            disabled={!osdDirty || saveOsd.isPending}
            onClick={() => void handleSaveOsd()}
            className="text-xs"
          >
            {saveOsd.isPending && <Loader2 className="size-3.5 animate-spin" />}
            Save overlays
          </Button>
        )}
      </div>
    </div>
  );
};

export const LiveCameraSettingsSheet: React.FC<LiveCameraSettingsSheetProps> = ({
  serial,
  cameraName,
  channel,
  onClose,
}) => {
  if (serial === null) return null;
  return (
    <LiveCameraSettingsSheetBody
      serial={serial}
      cameraName={cameraName}
      channel={channel}
      onClose={onClose}
    />
  );
};

