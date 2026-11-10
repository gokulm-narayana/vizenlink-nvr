import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SettingsForm } from "../SettingsForm";
import { useSaveOsd, type CameraSettingsData, type OsdItemPayload } from "../api";
import { CAMERAS_COPY } from "../copy";

export interface OverlaysTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

const POSITION_OPTIONS = [
  { value: "UpperLeft", label: "Top Left" },
  { value: "UpperRight", label: "Top Right" },
  { value: "BottomLeft", label: "Bottom Left" },
  { value: "BottomRight", label: "Bottom Right" },
];

export const OverlaysTab: React.FC<OverlaysTabProps> = ({
  serial,
  cameraName,
  settings,
}) => {
  const osdList = settings.osd || [];
  const tsOsd = osdList.find((o) => o.osd_type === "DateAndTime");
  const txtOsd = osdList.find((o) => o.osd_type === "Plain");

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const saveMutation = useSaveOsd(serial);

  const [form, setForm] = useState({
    timestampPos: tsOsd?.position || "UpperLeft",
    textPos: txtOsd?.position || "BottomRight",
    plainText: txtOsd?.plain_text || "",
  });

  const [isDirty, setIsDirty] = useState<boolean>(false);

  useEffect(() => {
    setForm({
      timestampPos: tsOsd?.position || "UpperLeft",
      textPos: txtOsd?.position || "BottomRight",
      plainText: txtOsd?.plain_text || "",
    });
    setIsDirty(false);
    setErrorMessage(null);
  }, [tsOsd, txtOsd, serial]);

  const handleFieldChange = (field: keyof typeof form, val: string) => {
    setForm((prev) => ({ ...prev, [field]: val }));
    setIsDirty(true);
  };

  const handleDiscard = () => {
    setForm({
      timestampPos: tsOsd?.position || "UpperLeft",
      textPos: txtOsd?.position || "BottomRight",
      plainText: txtOsd?.plain_text || "",
    });
    setIsDirty(false);
    setErrorMessage(null);
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    try {
      const payloads: OsdItemPayload[] = [
        {
          token: txtOsd?.token || "OSD_Text",
          video_source_token: txtOsd?.video_source_token || "VideoSource_1",
          osd_type: "Plain",
          position: form.textPos,
          plain_text: form.plainText,
        },
        {
          token: tsOsd?.token || "OSD_Time",
          video_source_token: tsOsd?.video_source_token || "VideoSource_1",
          osd_type: "DateAndTime",
          position: form.timestampPos,
        },
      ];

      await saveMutation.mutateAsync(payloads);
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
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            On-Screen Display (OSD) Overlays
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 flex flex-col gap-4">
          {/* Timestamp Position */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="osd-timestamp-pos" className="text-xs font-semibold text-foreground">
              Date & Timestamp Position
            </label>
            <select
              id="osd-timestamp-pos"
              value={form.timestampPos}
              onChange={(e) => handleFieldChange("timestampPos", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {POSITION_OPTIONS.map((pos) => (
                <option key={pos.value} value={pos.value}>
                  {pos.label}
                </option>
              ))}
            </select>
          </div>

          {/* Custom Text / Camera Name */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="osd-custom-text" className="text-xs font-semibold text-foreground">
              Custom Title / Watermark
            </label>
            <Input
              id="osd-custom-text"
              value={form.plainText}
              onChange={(e) => handleFieldChange("plainText", e.target.value)}
              placeholder="e.g. Front Door Camera"
              className="text-xs"
            />
          </div>

          {/* Text Position */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="osd-text-pos" className="text-xs font-semibold text-foreground">
              Title Overlay Position
            </label>
            <select
              id="osd-text-pos"
              value={form.textPos}
              onChange={(e) => handleFieldChange("textPos", e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {POSITION_OPTIONS.map((pos) => (
                <option key={pos.value} value={pos.value}>
                  {pos.label}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>
    </SettingsForm>
  );
};