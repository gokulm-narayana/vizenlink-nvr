import React, { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
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

  const rebootMutation = useReboot(serial);

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
    <Card className="border border-border">
      <CardHeader>
        <CardTitle>{CAMERAS_COPY.MAINTENANCE_HEADING}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col divide-y divide-border">
        {/* Row 1: Reboot camera */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-4 first:pt-0">
          <div className="flex flex-col gap-1 min-w-0">
            <span className="text-sm font-semibold text-foreground">
              {CAMERAS_COPY.REBOOT_BUTTON}
            </span>
            <span className="text-xs text-muted-foreground">
              {CAMERAS_COPY.REBOOT_DESCRIPTION}
            </span>
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
          <div className="flex flex-col gap-1 min-w-0">
            <span className="text-sm font-semibold text-foreground">
              {CAMERAS_COPY.FACTORY_RESET_BUTTON}
            </span>
            <span className="text-xs text-muted-foreground">
              Restore the camera to factory defaults. Choose between keeping network settings or wiping all configuration.
            </span>
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
      </CardContent>

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
  );
};