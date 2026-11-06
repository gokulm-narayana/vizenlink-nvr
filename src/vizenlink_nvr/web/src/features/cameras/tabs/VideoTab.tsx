import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SettingsForm } from "../SettingsForm";
import { resolutionLabels } from "../capabilities";
import { useSaveEncoder, type CameraSettingsData } from "../api";
import { CAMERAS_COPY } from "../copy";

export interface VideoTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

export const VideoTab: React.FC<VideoTabProps> = ({
  serial,
  cameraName,
  settings,
}) => {
  const encoders = settings.encoders || [];
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const saveMutation = useSaveEncoder(serial);

  const currentEnc = encoders[selectedIdx] || encoders[0];

  const [form, setForm] = useState({
    encoding: currentEnc?.current.encoding || "H265",
    resolution: `${currentEnc?.current.width || 1920}x${currentEnc?.current.height || 1080}`,
    frameRate: currentEnc?.current.frame_rate_limit || 25,
    bitrate: currentEnc?.current.bitrate_limit_kbps || 2048,
    quality: currentEnc?.current.quality || 50,
  });

  const [isDirty, setIsDirty] = useState<boolean>(false);

  useEffect(() => {
    if (currentEnc) {
      setForm({
        encoding: currentEnc.current.encoding,
        resolution: `${currentEnc.current.width}x${currentEnc.current.height}`,
        frameRate: currentEnc.current.frame_rate_limit,
        bitrate: currentEnc.current.bitrate_limit_kbps,
        quality: currentEnc.current.quality,
      });
      setIsDirty(false);
      setErrorMessage(null);
    }
  }, [currentEnc, serial]);

  if (!currentEnc) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        No video encoder configurations reported by this camera.
      </div>
    );
  }

  const resOptions = resolutionLabels(currentEnc.options);
  const fpsRange = currentEnc.options.frame_rate_range || [1, 30];
  const bitrateRange = currentEnc.options.bitrate_range_kbps || [128, 8192];
  const qualityRange = currentEnc.options.quality_range || [1, 100];

  const handleFieldChange = (field: keyof typeof form, val: any) => {
    setForm((prev) => ({ ...prev, [field]: val }));
    setIsDirty(true);
  };

  const handleDiscard = () => {
    setForm({
      encoding: currentEnc.current.encoding,
      resolution: `${currentEnc.current.width}x${currentEnc.current.height}`,
      frameRate: currentEnc.current.frame_rate_limit,
      bitrate: currentEnc.current.bitrate_limit_kbps,
      quality: currentEnc.current.quality,
    });
    setIsDirty(false);
    setErrorMessage(null);
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    const [w, h] = form.resolution.split("x").map(Number);
    try {
      await saveMutation.mutateAsync({
        venc_token: currentEnc.venc_token,
        encoding: form.encoding,
        width: w || currentEnc.current.width,
        height: h || currentEnc.current.height,
        frame_rate_limit: Number(form.frameRate),
        bitrate_limit_kbps: Number(form.bitrate),
        quality: Number(form.quality),
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
      <Card className="border-border bg-card p-4 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold text-foreground">
            Video Encoder Settings
          </CardTitle>

          {encoders.length > 1 && (
            <div className="flex items-center gap-2">
              <label htmlFor="stream-select" className="text-xs text-muted-foreground font-normal">
                Stream:
              </label>
              <select
                id="stream-select"
                value={selectedIdx}
                onChange={(e) => {
                  setSelectedIdx(Number(e.target.value));
                  setIsDirty(false);
                }}
                className="h-8 rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {encoders.map((enc, idx) => (
                  <option key={enc.profile_token} value={idx}>
                    {enc.profile_name || `Stream ${idx + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}
        </CardHeader>

        <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Encoding */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="enc-format" className="text-xs font-semibold text-foreground">
              Video Codec
            </label>
            <select
              id="enc-format"
              value={form.encoding}
              onChange={(e) => handleFieldChange("encoding", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {currentEnc.options.encodings.map((codec) => (
                <option key={codec} value={codec}>
                  {codec}
                </option>
              ))}
            </select>
          </div>

          {/* Resolution */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="enc-resolution" className="text-xs font-semibold text-foreground">
              Resolution
            </label>
            <select
              id="enc-resolution"
              value={form.resolution}
              onChange={(e) => handleFieldChange("resolution", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {resOptions.map((res) => (
                <option key={res} value={res}>
                  {res}
                </option>
              ))}
            </select>
          </div>

          {/* Frame Rate */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="enc-fps" className="text-xs font-semibold text-foreground">
                Frame Rate (FPS)
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.frameRate} fps</span>
            </div>
            <Input
              id="enc-fps"
              type="number"
              min={fpsRange[0]}
              max={fpsRange[1]}
              value={form.frameRate}
              onChange={(e) => handleFieldChange("frameRate", Number(e.target.value))}
              className="text-xs"
            />
            <span className="text-xs text-muted-foreground">
              Allowed: {fpsRange[0]} - {fpsRange[1]} fps
            </span>
          </div>

          {/* Bitrate */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="enc-bitrate" className="text-xs font-semibold text-foreground">
                Bitrate (kbps)
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.bitrate} kbps</span>
            </div>
            <Input
              id="enc-bitrate"
              type="number"
              min={bitrateRange[0]}
              max={bitrateRange[1]}
              value={form.bitrate}
              onChange={(e) => handleFieldChange("bitrate", Number(e.target.value))}
              className="text-xs"
            />
            <span className="text-xs text-muted-foreground">
              Allowed: {bitrateRange[0]} - {bitrateRange[1]} kbps
            </span>
          </div>

          {/* Quality */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="enc-quality" className="text-xs font-semibold text-foreground">
                Compression Quality
              </label>
              <span className="text-xs font-mono text-muted-foreground">{form.quality}%</span>
            </div>
            <Input
              id="enc-quality"
              type="number"
              min={qualityRange[0]}
              max={qualityRange[1]}
              value={form.quality}
              onChange={(e) => handleFieldChange("quality", Number(e.target.value))}
              className="text-xs"
            />
            <span className="text-xs text-muted-foreground">
              Allowed: {qualityRange[0]} - {qualityRange[1]}
            </span>
          </div>
        </CardContent>
      </Card>
    </SettingsForm>
  );
};
