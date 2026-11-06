import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { TriangleAlert } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { SettingsForm } from "../SettingsForm";
import { isWdrVisible, availableNightVisionTypes } from "../capabilities";
import { useSaveImaging, type CameraSettingsData } from "../api";
import { CAMERAS_COPY } from "../copy";

export interface ImageTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

export const ImageTab: React.FC<ImageTabProps> = ({
  serial,
  cameraName,
  settings,
}) => {
  const imaging = settings.imaging;
  const current = imaging?.current;
  const options = imaging?.options;

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
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
      });
      setIsDirty(false);
      setErrorMessage(null);
    }
  }, [current, serial]);

  if (!imaging || !current || !options) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        No imaging options reported by this camera.
      </div>
    );
  }

  const wdrSupported = isWdrVisible(options);
  const nightVisionChoices = availableNightVisionTypes(options);
  const irCutModes = options.ir_cut_filter_modes?.length
    ? options.ir_cut_filter_modes
    : ["AUTO", "DAY", "NIGHT"];

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
    });
    setIsDirty(false);
    setErrorMessage(null);
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    try {
      await saveMutation.mutateAsync({
        brightness: Number(form.brightness),
        contrast: Number(form.contrast),
        color_saturation: Number(form.saturation),
        sharpness: Number(form.sharpness),
        ir_cut_filter: form.irCutFilter,
        wdr_mode: form.wdrMode,
        wdr_level: Number(form.wdrLevel),
        night_vision_type: form.nightVisionType,
        mirror_flip: form.mirrorFlip,
        anti_flicker: form.antiFlicker,
      });
      toast(CAMERAS_COPY.SETTINGS_SAVED);
      setIsDirty(false);
    } catch {
      setErrorMessage(CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  return (
    <SettingsForm
      isDirty={isDirty}
      isSubmitting={saveMutation.isPending}
      errorMessage={errorMessage}
      onDiscard={handleDiscard}
      onSubmit={handleSubmit}
      retryLabel={CAMERAS_COPY.RETRY_SAVE}
    >
      {/* Day / Night & Night Vision */}
      <Card className="border-border bg-card p-4 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            Day / Night & Night Vision
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-nv-type" className="text-xs font-semibold text-foreground">
              Night Vision Mode
            </label>
            <select
              id="img-nv-type"
              value={form.nightVisionType}
              onChange={(e) => handleFieldChange("nightVisionType", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
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
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-ircut" className="text-xs font-semibold text-foreground">
              IR Cut Filter
            </label>
            <select
              id="img-ircut"
              value={form.irCutFilter}
              onChange={(e) => handleFieldChange("irCutFilter", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {irCutModes.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {/* WDR (Hidden if not supported, not disabled) */}
      {wdrSupported && (
        <Card className="border-border bg-card p-4 flex flex-col gap-4">
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
                <select
                  id="img-wdr-mode"
                  value={form.wdrMode}
                  onChange={(e) => handleFieldChange("wdrMode", e.target.value)}
                  className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="OFF">Off</option>
                  <option value="ON">On</option>
                  <option value="AUTO">Auto</option>
                </select>
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
      <Card className="border-border bg-card p-4 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            Image Signal Processing (ISP)
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
            <select
              id="img-mirror"
              value={form.mirrorFlip}
              onChange={(e) => handleFieldChange("mirrorFlip", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="off">Normal</option>
              <option value="flip">Flip (Vertical)</option>
              <option value="mirror">Mirror (Horizontal)</option>
              <option value="flip_mirror">Flip & Mirror (180°)</option>
            </select>
          </div>

          {/* Anti-flicker */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="img-flicker" className="text-xs font-semibold text-foreground">
              Anti-Flicker Frequency
            </label>
            <select
              id="img-flicker"
              value={form.antiFlicker}
              onChange={(e) => handleFieldChange("antiFlicker", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="Auto">Auto</option>
              <option value="50Hz">50 Hz</option>
              <option value="60Hz">60 Hz</option>
              <option value="Off">Off</option>
            </select>
          </div>
        </CardContent>
      </Card>
    </SettingsForm>
  );
};
