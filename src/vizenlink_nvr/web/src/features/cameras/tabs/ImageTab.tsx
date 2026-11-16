import { NativeSelect } from "@/components/ui/native-select";
import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { TriangleAlert } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { SettingsForm } from "../SettingsForm";
import { isWdrVisible, availableNightVisionTypes } from "../capabilities";
import { useSaveImaging, type CameraSettingsData } from "../api";
import { CAMERAS_COPY } from "../copy";

const DAY_NIGHT_LABELS: Record<string, string> = {
  AUTO: "Auto (switches with light)",
  ON: "Day (colour)",
  OFF: "Night (infrared, black & white)",
};

export interface ImageTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

function previewFactor(value: number, saved: number, range: [number, number]) {
  return 1 + (value - saved) / Math.max(1, range[1] - range[0]);
}

const orientations: Record<string, [number, number]> = {
  off: [1, 1],
  mirror: [-1, 1],
  flip: [1, -1],
  flip_mirror: [-1, -1],
};

export const ImageTab: React.FC<ImageTabProps> = ({
  serial,
  cameraName,
  settings,
}) => {
  const imaging = settings.imaging;
  const current = imaging?.current;
  const options = imaging?.options;

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [snapshotVersion, setSnapshotVersion] = useState(0);
  const [snapshotError, setSnapshotError] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const saveMutation = useSaveImaging(serial);

  const [form, setForm] = useState({
    brightness: current?.brightness ?? 50,
    contrast: current?.contrast ?? 50,
    saturation: current?.color_saturation ?? 50,
    sharpness: current?.sharpness ?? 50,
    irCutFilter: current?.ir_cut_filter ?? "AUTO",
    wdrMode: current?.wdr_mode ?? "OFF",
    wdrLevel: current?.wdr_level ?? 0,
    nightVisionType: current?.night_vision_type ?? "grey",
    mirrorFlip: current?.mirror_flip ?? "off",
    antiFlicker: current?.anti_flicker ?? "Auto",
    exposureMode: current?.exposure_mode ?? "",
    exposureTime: current?.exposure_time ?? 0,
    exposureGain: current?.exposure_gain ?? 0,
    whiteBalanceMode: current?.white_balance_mode ?? "",
  });

  const [isDirty, setIsDirty] = useState<boolean>(false);

  useEffect(() => {
    if (current) {
      setForm({
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
      });
      setIsDirty(false);
      setErrorMessage(null);
      setShowSaved(false);
    }
  }, [current, serial]);

  useEffect(() => {
    setSnapshotError(false);
  }, [serial]);

  if (!imaging || !current || !options) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        No imaging options reported by this camera.
      </div>
    );
  }

  const wdrSupported = isWdrVisible(options);
  const nightVisionChoices = availableNightVisionTypes(options);
  // Day/Night mode is ONVIF IrCutFilter (SETTINGS_API_GUIDE): ON = day/colour, OFF = night/IR,
  // AUTO = switch with light. The camera's own list is the only valid choice set; empty = not offered.
  const irCutModes = options.ir_cut_filter_modes ?? [];
  const dayNightNow = current?.day_night_now ?? null;

  // Exposure / white balance (old VMS parity): the camera owns the choice lists.
  const exposureModes = options.exposure_modes ?? [];
  const whiteBalanceModes = options.white_balance_modes ?? [];
  const isManualExposure = form.exposureMode.toUpperCase() === "MANUAL";
  const showExposureCard = exposureModes.length > 0 || whiteBalanceModes.length > 0;
  const modeLabel = (m: string) => m.charAt(0) + m.slice(1).toLowerCase();
  const snapshotUrl = `/api/v1/cameras/${encodeURIComponent(serial)}/snapshot?profile=medium&v=${snapshotVersion}`;
  const brightness = previewFactor(form.brightness, current.brightness, options.brightness_range ?? [0, 100]);
  const contrast = previewFactor(form.contrast, current.contrast, options.contrast_range ?? [0, 100]);
  const saturation = previewFactor(form.saturation, current.color_saturation, options.color_saturation_range ?? [0, 100]);
  const [draftX, draftY] = orientations[form.mirrorFlip] ?? orientations.off;
  const [savedX, savedY] = orientations[current.mirror_flip] ?? orientations.off;
  const hasVisualDraft = isDirty && (brightness !== 1 || contrast !== 1 || saturation !== 1 || draftX !== savedX || draftY !== savedY);
  const showDraft = hasVisualDraft && !showSaved;

  const refreshSnapshot = () => {
    setSnapshotError(false);
    setSnapshotVersion((version) => version + 1);
  };

  const handleFieldChange = (field: keyof typeof form, val: any) => {
    setForm((prev) => ({ ...prev, [field]: val }));
    setIsDirty(true);
  };

  const handleDiscard = () => {
    setForm({
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
    });
    setIsDirty(false);
    setErrorMessage(null);
    setShowSaved(false);
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    try {
      await saveMutation.mutateAsync({
        brightness: Number(form.brightness),
        contrast: Number(form.contrast),
        color_saturation: Number(form.saturation),
        sharpness: Number(form.sharpness),
        ...(irCutModes.length ? { ir_cut_filter: form.irCutFilter } : {}),
        ...(wdrSupported ? { wdr_mode: form.wdrMode, wdr_level: Number(form.wdrLevel) } : {}),
        night_vision_type: form.nightVisionType,
        mirror_flip: form.mirrorFlip,
        anti_flicker: form.antiFlicker,
        // Only send what the camera offers; time/gain only apply in manual exposure.
        ...(exposureModes.length && form.exposureMode ? { exposure_mode: form.exposureMode } : {}),
        ...(isManualExposure && options.exposure_time_range ? { exposure_time: Number(form.exposureTime) } : {}),
        ...(isManualExposure && options.exposure_gain_range ? { exposure_gain: Number(form.exposureGain) } : {}),
        ...(whiteBalanceModes.length && form.whiteBalanceMode ? { white_balance_mode: form.whiteBalanceMode } : {}),
      });
      toast(CAMERAS_COPY.SETTINGS_SAVED);
      setIsDirty(false);
      setShowSaved(false);
      refreshSnapshot();
    } catch {
      setErrorMessage(CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Image &amp; night mode</h2>
        <p className="mt-1 text-sm text-muted-foreground">Adjust day/night switching, infrared or full-color night vision, WDR, and picture levels with live preview.</p>
      </div>
      <SettingsForm
        isDirty={isDirty}
        isSubmitting={saveMutation.isPending}
        errorMessage={errorMessage}
        onDiscard={handleDiscard}
        onSubmit={handleSubmit}
        retryLabel={CAMERAS_COPY.RETRY_SAVE}
      >
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <aside className="order-2 xl:sticky xl:top-4">
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm font-semibold">Preview</CardTitle>
            <div className="flex flex-wrap gap-2">
              {hasVisualDraft && !snapshotError && (
                <Button type="button" size="sm" variant="outline" aria-pressed={showSaved} onClick={() => setShowSaved(!showSaved)}>
                  Show saved image
                </Button>
              )}
              <Button type="button" size="sm" variant="outline" onClick={refreshSnapshot} disabled={saveMutation.isPending}>
                Refresh snapshot
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0 flex flex-col gap-2">
            <div className="aspect-video w-full max-w-sm overflow-hidden rounded-lg bg-video-bg xl:max-w-none">
              {snapshotError ? (
                <p role="status" className="grid size-full place-items-center p-4 text-center text-sm text-video-fg">
                  Camera snapshot unavailable. Try refreshing the snapshot.
                </p>
              ) : (
                <img
                  key={snapshotUrl}
                  src={snapshotUrl}
                  alt={`${cameraName} ${showDraft ? "estimated image preview" : "camera snapshot"}`}
                  className="size-full object-contain"
                  onError={() => setSnapshotError(true)}
                  style={showDraft ? {
                    // dynamic-style: live estimated ISP slider preview
                    filter: `brightness(${brightness}) contrast(${contrast}) saturate(${saturation})`,
                    transform: `scale(${draftX * savedX}, ${draftY * savedY})`,
                  } : undefined}
                />
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {showDraft
                ? "Estimated preview. Other changes appear after you save."
                : "Latest snapshot from the camera."}
            </p>
          </CardContent>
        </Card>
        </aside>
        <div className="order-1 flex min-w-0 flex-col gap-4">

        {/* Day / Night & Night Vision */}
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">
              Day &amp; night
            </CardTitle>
          </CardHeader>
        <CardContent className="p-0 grid grid-cols-1 gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-ircut" className="text-xs font-semibold text-foreground">
              Day / night mode
            </label>
            {irCutModes.length > 0 ? (
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-2" role="group" aria-label="Quick day or night mode">
                  {irCutModes.map((mode) => {
                    const active = form.irCutFilter.toUpperCase() === mode.toUpperCase();
                    return (
                      <Button
                        key={mode}
                        type="button"
                        size="sm"
                        variant={active ? "default" : "outline"}
                        aria-pressed={active}
                        onClick={() => handleFieldChange("irCutFilter", mode)}
                      >
                        {mode.toUpperCase() === "AUTO" ? "Auto" : mode.toUpperCase() === "ON" ? "Day (Colour)" : mode.toUpperCase() === "OFF" ? "Night (Infrared)" : mode}
                      </Button>
                    );
                  })}
                </div>
                <NativeSelect
                  id="img-ircut"
                  value={form.irCutFilter}
                  onChange={(e) => handleFieldChange("irCutFilter", e.target.value)}
                >
                  {irCutModes.map((mode) => (
                    <option key={mode} value={mode}>
                      {DAY_NIGHT_LABELS[mode.toUpperCase()] ?? mode}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Not available on this camera.</p>
            )}
            {dayNightNow && (
              <p role="status" className="text-xs text-muted-foreground">
                Right now: {dayNightNow === "day" ? "Day (colour)" : "Night (infrared)"}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-nv-type" className="text-xs font-semibold text-foreground">
              Night Vision Mode
            </label>
            <NativeSelect
              id="img-nv-type"
              value={form.nightVisionType}
              onChange={(e) => handleFieldChange("nightVisionType", e.target.value)}
            >
              {nightVisionChoices.map((t) => (
                <option key={t} value={t}>
                  {t === "grey"
                    ? "Infrared (Black & White)"
                    : t === "color"
                      ? "Full Color Night Vision"
                      : "Smart Dual-Mode (Color on Motion)"}
                </option>
              ))}
            </NativeSelect>
          </div>

        </CardContent>
      </Card>

      {/* WDR (Hidden if not supported, not disabled) */}
      {wdrSupported && (
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">
              Wide Dynamic Range (WDR)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex flex-col gap-4">
            <Alert variant="default" className="border-warning/40 bg-warning-subtle text-foreground flex items-center gap-2">
              <TriangleAlert className="h-4 w-4 shrink-0 text-warning" />
              <AlertDescription className="text-xs">
                {CAMERAS_COPY.WDR_WARNING}
              </AlertDescription>
            </Alert>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="img-wdr-mode" className="text-xs font-semibold text-foreground">
                  WDR Mode
                </label>
                <NativeSelect
                  id="img-wdr-mode"
                  value={form.wdrMode}
                  onChange={(e) => handleFieldChange("wdrMode", e.target.value)}
                >
                  <option value="OFF">Off</option>
                  <option value="ON">On</option>
                  <option value="AUTO">Auto</option>
                </NativeSelect>
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between items-center">
                  <label htmlFor="img-wdr-level" className="text-xs font-semibold text-foreground">
                    WDR Strength Level
                  </label>
                  <span className="text-xs font-mono text-muted-foreground">{form.wdrLevel}</span>
                </div>
                <input
                  id="img-wdr-level"
                  type="range"
                  min={options.wdr_level_range?.[0] ?? 0}
                  max={options.wdr_level_range?.[1] ?? 100}
                  value={form.wdrLevel}
                  onChange={(e) => handleFieldChange("wdrLevel", Number(e.target.value))}
                  className="h-2 w-full cursor-pointer accent-primary"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ISP Sliders */}
      <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            Picture
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Brightness */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="img-bright" className="text-xs font-semibold text-foreground">
                Brightness
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.brightness}</span>
            </div>
            <input
              id="img-bright"
              type="range"
              min={options.brightness_range?.[0] ?? 0}
              max={options.brightness_range?.[1] ?? 100}
              value={form.brightness}
              onChange={(e) => handleFieldChange("brightness", Number(e.target.value))}
              className="h-2 w-full cursor-pointer accent-primary"
            />
          </div>

          {/* Contrast */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="img-contrast" className="text-xs font-semibold text-foreground">
                Contrast
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.contrast}</span>
            </div>
            <input
              id="img-contrast"
              type="range"
              min={options.contrast_range?.[0] ?? 0}
              max={options.contrast_range?.[1] ?? 100}
              value={form.contrast}
              onChange={(e) => handleFieldChange("contrast", Number(e.target.value))}
              className="h-2 w-full cursor-pointer accent-primary"
            />
          </div>

          {/* Saturation */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="img-sat" className="text-xs font-semibold text-foreground">
                Color Saturation
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.saturation}</span>
            </div>
            <input
              id="img-sat"
              type="range"
              min={options.color_saturation_range?.[0] ?? 0}
              max={options.color_saturation_range?.[1] ?? 100}
              value={form.saturation}
              onChange={(e) => handleFieldChange("saturation", Number(e.target.value))}
              className="h-2 w-full cursor-pointer accent-primary"
            />
          </div>

          {/* Sharpness */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="img-sharp" className="text-xs font-semibold text-foreground">
                Sharpness
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.sharpness}</span>
            </div>
            <input
              id="img-sharp"
              type="range"
              min={options.sharpness_range?.[0] ?? 0}
              max={options.sharpness_range?.[1] ?? 100}
              value={form.sharpness}
              onChange={(e) => handleFieldChange("sharpness", Number(e.target.value))}
              className="h-2 w-full cursor-pointer accent-primary"
            />
          </div>

          {/* Mirror / Flip */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-mirror" className="text-xs font-semibold text-foreground">
              Orientation
            </label>
            <NativeSelect
              id="img-mirror"
              value={form.mirrorFlip}
              onChange={(e) => handleFieldChange("mirrorFlip", e.target.value)}
            >
              <option value="off">Normal</option>
              <option value="flip">Flip (Vertical)</option>
              <option value="mirror">Mirror (Horizontal)</option>
              <option value="flip_mirror">Flip & Mirror (180°)</option>
            </NativeSelect>
          </div>

          {/* Anti-flicker */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-flicker" className="text-xs font-semibold text-foreground">
              Anti-Flicker Frequency
            </label>
            <NativeSelect
              id="img-flicker"
              value={form.antiFlicker}
              onChange={(e) => handleFieldChange("antiFlicker", e.target.value)}
            >
              <option value="Auto">Auto</option>
              <option value="50Hz">50 Hz</option>
              <option value="60Hz">60 Hz</option>
              <option value="Off">Off</option>
            </NativeSelect>
          </div>
        </CardContent>
      </Card>
      {showExposureCard && (
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">Exposure &amp; White Balance</CardTitle>
          </CardHeader>
          <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4">
            {exposureModes.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="img-exposure-mode" className="text-xs font-semibold text-foreground">
                  Exposure Control
                </label>
                <NativeSelect
                  id="img-exposure-mode"
                  value={form.exposureMode}
                  onChange={(e) => handleFieldChange("exposureMode", e.target.value)}
                >
                  {!form.exposureMode && <option value="">Camera default</option>}
                  {exposureModes.map((m) => (
                    <option key={m} value={m}>
                      {modeLabel(m)}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
            {whiteBalanceModes.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="img-wb-mode" className="text-xs font-semibold text-foreground">
                  White Balance Mode
                </label>
                <NativeSelect
                  id="img-wb-mode"
                  value={form.whiteBalanceMode}
                  onChange={(e) => handleFieldChange("whiteBalanceMode", e.target.value)}
                >
                  {!form.whiteBalanceMode && <option value="">Camera default</option>}
                  {whiteBalanceModes.map((m) => (
                    <option key={m} value={m}>
                      {modeLabel(m)}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
            {isManualExposure && options.exposure_time_range && (
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between items-center">
                  <label htmlFor="img-exposure-time" className="text-xs font-semibold text-foreground">
                    Exposure Time (µs)
                  </label>
                  <span className="text-xs font-mono text-muted-foreground">{form.exposureTime}</span>
                </div>
                <input
                  id="img-exposure-time"
                  type="range"
                  min={options.exposure_time_range[0]}
                  max={options.exposure_time_range[1]}
                  value={form.exposureTime}
                  onChange={(e) => handleFieldChange("exposureTime", Number(e.target.value))}
                  className="h-2 w-full cursor-pointer accent-primary"
                />
              </div>
            )}
            {isManualExposure && options.exposure_gain_range && (
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between items-center">
                  <label htmlFor="img-exposure-gain" className="text-xs font-semibold text-foreground">
                    Gain
                  </label>
                  <span className="text-xs font-mono text-muted-foreground">{form.exposureGain}</span>
                </div>
                <input
                  id="img-exposure-gain"
                  type="range"
                  min={options.exposure_gain_range[0]}
                  max={options.exposure_gain_range[1]}
                  value={form.exposureGain}
                  onChange={(e) => handleFieldChange("exposureGain", Number(e.target.value))}
                  className="h-2 w-full cursor-pointer accent-primary"
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}
      </div>
      </div>
      </SettingsForm>
    </div>
  );
};
