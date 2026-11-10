import React, { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/PasswordField";
import { SettingsForm } from "../SettingsForm";
import { useSaveIdentity, type CameraSettingsData } from "../api";
import { CAMERAS_COPY } from "../copy";

const identitySchema = z.object({
  name: z.string().min(1, "Camera name is required"),
  location: z.string().optional(),
  timezone: z.string().optional(),
  password: z.string().optional(),
});

type IdentityFormValues = z.infer<typeof identitySchema>;

export interface IdentityTabProps {
  serial: string;
  cameraName: string;
  settings: CameraSettingsData;
}

export const IdentityTab: React.FC<IdentityTabProps> = ({
  serial,
  cameraName,
  settings,
}) => {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const saveMutation = useSaveIdentity(serial);

  const {
    register,
    handleSubmit,
    reset,
    formState: { isDirty, isSubmitting, errors },
  } = useForm<IdentityFormValues>({
    resolver: zodResolver(identitySchema),
    defaultValues: {
      name: settings.identity.name || "",
      location: settings.identity.location || "",
      timezone: settings.identity.timezone || "UTC",
      password: "",
    },
  });

  // Re-sync form when camera serial or settings change
  useEffect(() => {
    reset({
      name: settings.identity.name || "",
      location: settings.identity.location || "",
      timezone: settings.identity.timezone || "UTC",
      password: "",
    });
    setErrorMessage(null);
  }, [serial, settings, reset]);

  const onSubmit = async (values: IdentityFormValues) => {
    setErrorMessage(null);
    try {
      const payload: Record<string, string> = {
        name: values.name,
      };
      if (values.location !== undefined) payload.location = values.location;
      if (values.timezone) payload.timezone = values.timezone;
      if (values.password) payload.password = values.password;

      await saveMutation.mutateAsync(payload);
      toast(CAMERAS_COPY.SETTINGS_SAVED);
      reset({
        name: values.name,
        location: values.location || "",
        timezone: values.timezone || "UTC",
        password: "",
      });
    } catch {
      setErrorMessage(CAMERAS_COPY.SAVE_FAILED(cameraName));
    }
  };

  const handleDiscard = () => {
    reset({
      name: settings.identity.name || "",
      location: settings.identity.location || "",
      timezone: settings.identity.timezone || "UTC",
      password: "",
    });
    setErrorMessage(null);
  };

  return (
    <SettingsForm
      isDirty={isDirty}
      isSubmitting={isSubmitting || saveMutation.isPending}
      errorMessage={errorMessage}
      onDiscard={handleDiscard}
      onSubmit={handleSubmit(onSubmit)}
      retryLabel={CAMERAS_COPY.RETRY_SAVE}
    >
      {/* Device Identity */}
      <Card className="border-border bg-card p-4 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            Identity & Credentials
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="cam-name" className="text-xs font-semibold text-foreground">
              Camera name
            </label>
            <Input
              id="cam-name"
              {...register("name")}
              placeholder="e.g. Front Door"
              className="text-xs"
            />
            {errors.name && (
              <span className="text-xs text-critical">{errors.name.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="cam-location" className="text-xs font-semibold text-foreground">
              Location
            </label>
            <Input
              id="cam-location"
              {...register("location")}
              placeholder="e.g. Building A - Floor 1"
              className="text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="cam-timezone" className="text-xs font-semibold text-foreground">
              Time zone
            </label>
            <select
              id="cam-timezone"
              {...register("timezone")}
              className="h-9 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {settings.identity.supported_timezones &&
              settings.identity.supported_timezones.length > 0 ? (
                settings.identity.supported_timezones.map((tz) => (
                  <option key={tz.code} value={tz.code}>
                    {tz.label} ({tz.code})
                  </option>
                ))
              ) : (
                <>
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">Eastern Time (America/New_York)</option>
                  <option value="America/Chicago">Central Time (America/Chicago)</option>
                  <option value="America/Denver">Mountain Time (America/Denver)</option>
                  <option value="America/Los_Angeles">Pacific Time (America/Los_Angeles)</option>
                  <option value="Asia/Kolkata">India Standard Time (Asia/Kolkata)</option>
                  <option value="Europe/London">Greenwich Mean Time (Europe/London)</option>
                </>
              )}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="cam-password" className="text-xs font-semibold text-foreground">
              Camera password
            </label>
            <PasswordField
              id="cam-password"
              {...register("password")}
              placeholder="Leave blank to keep current password"
              autoComplete="new-password"
              className="text-xs"
            />
            <span className="text-xs text-muted-foreground">
              The NVR stores it encrypted and never shows it again.
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Hardware & Build Info (Read-only) */}
      <Card className="border-border bg-card p-4 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            Hardware & Build Info
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground font-normal">Manufacturer</span>
            <span className="font-semibold text-foreground">
              {settings.device_info.manufacturer || "Unknown"}
            </span>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground font-normal">Model</span>
            <span className="font-semibold text-foreground">
              {settings.device_info.model || "Unknown"}
            </span>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground font-normal">Firmware Version</span>
            <span className="font-semibold text-foreground font-mono">
              {settings.device_info.firmware_version || "Unknown"}
            </span>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground font-normal">Serial Number</span>
            <span className="font-semibold text-foreground font-mono">
              {settings.device_info.serial_number || serial}
            </span>
          </div>

          <div className="flex flex-col gap-0.5 sm:col-span-2">
            <span className="text-muted-foreground font-normal">Hardware ID</span>
            <span className="font-semibold text-foreground font-mono break-all">
              {settings.device_info.hardware_id || "Unknown"}
            </span>
          </div>
        </CardContent>
      </Card>
    </SettingsForm>
  );
};