import React, { useState } from "react";
import { AlertTriangle, RotateCcw, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { FactoryResetDialog } from "../FactoryResetDialog";
import { useReboot } from "../api";
import { CAMERAS_COPY } from "../copy";

export interface MaintenanceTabProps {
  serial: string;
  cameraName: string;
}

export const MaintenanceTab: React.FC<MaintenanceTabProps> = ({
  serial,
  cameraName,
}) => {
  const [showRebootDialog, setShowRebootDialog] = useState<boolean>(false);
  const [rebootError, setRebootError] = useState<boolean>(false);
  const [showResetDialog, setShowResetDialog] = useState<boolean>(false);
  const [showRemoveDialog, setShowRemoveDialog] = useState(false);

  const rebootMutation = useReboot(serial);
  const owner = useCurrentUser()?.role === "owner";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const removeCamera = useMutation({
    mutationFn: () => apiFetch(`/api/v1/cameras/${encodeURIComponent(serial)}?keep_recordings=true`, {
      method: "DELETE",
    }),
    onSuccess: () => {
      toast.success(`${cameraName} removed from the recorder`);
      void queryClient.invalidateQueries({ queryKey: ["cameras"] });
      navigate("/cameras", { replace: true });
    },
  });

  const handleReboot = async () => {
    setRebootError(false);
    try {
      await rebootMutation.mutateAsync();
      toast.success(CAMERAS_COPY.REBOOT_STARTED(cameraName));
      setShowRebootDialog(false);
    } catch {
      setRebootError(true);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">{CAMERAS_COPY.MAINTENANCE_HEADING}</h2>
        <p className="mt-1 text-sm text-muted-foreground">Restart the device, restore factory configuration, or unpair it from this recorder.</p>
      </div>
      <Card className="rounded-xl border border-border bg-card p-6">
        <CardContent className="p-0 flex flex-col divide-y divide-border">
          {/* Row 1: Reboot camera */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-4 first:pt-0">
            <div className="flex items-start gap-4 min-w-0">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-selected text-primary">
                <RotateCcw className="size-4" />
              </span>
              <div className="flex flex-col gap-1 min-w-0">
                <span className="text-sm font-semibold text-foreground">
                  {CAMERAS_COPY.REBOOT_BUTTON}
                </span>
                <span className="text-xs text-muted-foreground">
                  {CAMERAS_COPY.REBOOT_DESCRIPTION}
                </span>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setRebootError(false);
                setShowRebootDialog(true);
              }}
              className="shrink-0 self-start sm:self-center"
            >
              {CAMERAS_COPY.REBOOT_BUTTON}
            </Button>
          </div>

          {/* Row 2: Factory reset camera */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-4 last:pb-0">
            <div className="flex items-start gap-4 min-w-0">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-critical-subtle text-critical">
                <AlertTriangle className="size-4" />
              </span>
              <div className="flex flex-col gap-1 min-w-0">
                <span className="text-sm font-semibold text-foreground">
                  {CAMERAS_COPY.FACTORY_RESET_BUTTON}
                </span>
                <span className="text-xs text-muted-foreground">
                  Restore the camera to factory defaults. Choose between keeping network settings or wiping all configuration.
                </span>
              </div>
            </div>
            <Button
              type="button"
              variant="destructive"
              onClick={() => setShowResetDialog(true)}
              className="shrink-0 self-start sm:self-center"
            >
              {CAMERAS_COPY.FACTORY_RESET_BUTTON}
            </Button>
          </div>
          {owner && (
            <div className="flex flex-col justify-between gap-4 py-4 last:pb-0 sm:flex-row sm:items-center">
              <div className="flex items-start gap-4 min-w-0">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Trash2 className="size-4" />
                </span>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="text-sm font-semibold">Remove camera</span>
                  <span className="text-xs text-muted-foreground">Remove this camera from the recorder so you can add it again.</span>
                </div>
              </div>
              <Button type="button" variant="outline" className="shrink-0 self-start sm:self-center"
                onClick={() => { removeCamera.reset(); setShowRemoveDialog(true); }}>
                Remove camera
              </Button>
            </div>
          )}
        </CardContent>

      {owner && (
        <AlertDialog open={showRemoveDialog} onOpenChange={open => {
          if (!removeCamera.isPending) setShowRemoveDialog(open);
        }}>
          <AlertDialogContent className="sm:max-w-md">
            <AlertDialogHeader>
              <AlertDialogTitle>Remove {cameraName}?</AlertDialogTitle>
              <AlertDialogDescription>
                This removes the camera and its saved connection settings from the NVR. Owners and operators can still open its saved footage in Playback under the archived camera name.
              </AlertDialogDescription>
            </AlertDialogHeader>
            {removeCamera.error && <p role="alert" className="text-sm text-critical">{removeCamera.error.message}</p>}
            <AlertDialogFooter>
              <AlertDialogCancel disabled={removeCamera.isPending}>Keep camera</AlertDialogCancel>
              <Button type="button" variant="destructive" disabled={removeCamera.isPending} onClick={() => removeCamera.mutate()}>
                {removeCamera.isPending ? "Removing camera…" : "Remove camera"}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}

      {/* Reboot Alert Dialog */}
      <AlertDialog
        open={showRebootDialog}
        onOpenChange={(open) => {
          if (!open) {
            setRebootError(false);
            setShowRebootDialog(false);
          } else {
            setShowRebootDialog(true);
          }
        }}
      >
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{CAMERAS_COPY.REBOOT_TITLE(cameraName)}</AlertDialogTitle>
            <AlertDialogDescription>
              {CAMERAS_COPY.REBOOT_DESCRIPTION}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {rebootError && (
            <div className="py-2">
              <InlineError
                message={CAMERAS_COPY.REBOOT_FAILED(cameraName)}
                actionLabel={CAMERAS_COPY.RETRY_REBOOT}
                onAction={handleReboot}
                pending={rebootMutation.isPending}
              />
            </div>
          )}

          <AlertDialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setRebootError(false);
                setShowRebootDialog(false);
              }}
              disabled={rebootMutation.isPending}
            >
              {CAMERAS_COPY.KEEP_RUNNING_BUTTON}
            </Button>
            <Button
              type="button"
              variant="default"
              onClick={handleReboot}
              disabled={rebootMutation.isPending}
            >
              {rebootMutation.isPending && (
                <Spinner className="mr-2 h-4 w-4" />
              )}
              {CAMERAS_COPY.REBOOT_BUTTON}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Factory Reset Dialog */}
      <FactoryResetDialog
        open={showResetDialog}
        onOpenChange={setShowResetDialog}
        serial={serial}
        cameraName={cameraName}
      />
    </Card>
    </div>
  );
};
