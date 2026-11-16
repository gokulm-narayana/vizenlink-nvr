import { NativeSelect } from "@/components/ui/native-select";
import { useCameras } from "@/lib/queries";
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
  // Old VMS showed the MAC; the NVR registry already stores it (from onboarding / discovery).
  const { data: cameras } = useCameras();
  const macAddress = (Array.isArray(cameras) ? cameras : []).find((c) => c.serial === serial)?.mac as string | undefined;

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
      timezone: settings.identity.timezone || "",
      password: "",
    },
  });

  // Re-sync form when camera serial or settings change
  useEffect(() => {
    reset({
      name: settings.identity.name || "",
      location: settings.identity.location || "",
      timezone: settings.identity.timezone || "",
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
        timezone: values.timezone || "",
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
      timezone: settings.identity.timezone || "",
      password: "",
    });
    setErrorMessage(null);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Details</h2>
        <p className="mt-1 text-sm text-muted-foreground">Camera name, location, time zone, credentials, and hardware identity.</p>
      </div>
      <SettingsForm
        isDirty={isDirty}
        isSubmitting={isSubmitting || saveMutation.isPending}
        errorMessage={errorMessage}
        onDiscard={handleDiscard}
        onSubmit={handleSubmit(onSubmit)}
        retryLabel={CAMERAS_COPY.RETRY_SAVE}
      >
        {/* Device Identity */}
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">
              Identity &amp; Credentials
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label htmlFor="cam-name" className="text-sm font-semibold text-foreground">
                Camera name
              </label>
              <Input
                id="cam-name"
                {...register("name")}
                placeholder="e.g. Front Door"
              />
              {errors.name && (
                <span className="text-xs text-critical">{errors.name.message}</span>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="cam-location" className="text-sm font-semibold text-foreground">
                Location
              </label>
              <Input
                id="cam-location"
                {...register("location")}
                placeholder="e.g. Building A - Floor 1"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="cam-timezone" className="text-sm font-semibold text-foreground">
                Time zone
              </label>
              <NativeSelect
                id="cam-timezone"
                {...register("timezone")}
              >
                <option value="">Time zone not reported — choose to change</option>
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
              </NativeSelect>
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="cam-password" className="text-sm font-semibold text-foreground">
                Camera password
              </label>
              <PasswordField
                id="cam-password"
                {...register("password")}
                placeholder="Leave blank to keep current password"
                autoComplete="new-password"
              />
              <span className="text-xs text-muted-foreground">
                The NVR stores it encrypted and never shows it again.
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Hardware & Build Info (Read-only) */}
        <Card className="rounded-xl border-border bg-card p-6 flex flex-col gap-4">
          <CardHeader className="p-0 pb-2 border-b border-border">
            <CardTitle className="text-sm font-semibold text-foreground">
              Hardware &amp; Build Info
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">Manufacturer</span>
              <span className="font-semibold text-foreground">
                {settings.device_info.manufacturer || "Unknown"}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">Model</span>
              <span className="font-semibold text-foreground">
                {settings.device_info.model || "Unknown"}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">Firmware Version</span>
              <span className="font-semibold text-foreground font-mono">
                {settings.device_info.firmware_version || "Unknown"}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">Serial Number</span>
              <span className="font-semibold text-foreground font-mono">
                {settings.device_info.serial_number || serial}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">MAC Address</span>
              <span className="font-semibold text-foreground font-mono">{macAddress || "Unknown"}</span>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-normal">Hardware ID</span>
              <span className="font-semibold text-foreground font-mono break-all">
                {settings.device_info.hardware_id || "Unknown"}
              </span>
            </div>
          </CardContent>
        </Card>
      </SettingsForm>
    </div>
  );
};