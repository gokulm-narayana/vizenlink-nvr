import React, { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { useFactoryReset } from "./api";
import { CAMERAS_COPY } from "./copy";

export interface FactoryResetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  serial: string;
  cameraName: string;
}

export const FactoryResetDialog: React.FC<FactoryResetDialogProps> = ({
  open,
  onOpenChange,
  serial,
  cameraName,
}) => {
  const [step, setStep] = useState<1 | 2>(1);
  const [mode, setMode] = useState<"Soft" | "Hard">("Soft");
  const [confirmInput, setConfirmInput] = useState<string>("");
  const [hasError, setHasError] = useState<boolean>(false);

  const resetMutation = useFactoryReset(serial);

  const handleClose = () => {
    setStep(1);
    setMode("Soft");
    setConfirmInput("");
    setHasError(false);
    onOpenChange(false);
  };

  const handleReset = async () => {
    setHasError(false);
    try {
      await resetMutation.mutateAsync({
        mode,
        confirmation: "RESET",
      });
      const toastMessage =
        mode === "Soft"
          ? CAMERAS_COPY.SOFT_RESET_STARTED(cameraName)
          : CAMERAS_COPY.HARD_RESET_STARTED(cameraName);
      toast.success(toastMessage);
      handleClose();
    } catch {
      setHasError(true);
    }
  };

  const isConfirmed = confirmInput.trim().toUpperCase() === "RESET";

  const selectedDesc =
    mode === "Soft"
      ? CAMERAS_COPY.SOFT_RESET_DESC(cameraName)
      : CAMERAS_COPY.HARD_RESET_DESC(cameraName);

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) handleClose();
        else onOpenChange(true);
      }}
    >
      <AlertDialogContent className="sm:max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle>{CAMERAS_COPY.FACTORY_RESET_BUTTON}</AlertDialogTitle>
          <AlertDialogDescription>
            {step === 1 ? (
              <span className="sr-only">{CAMERAS_COPY.RESET_MODE_LABEL}</span>
            ) : mode === "Soft" ? (
              CAMERAS_COPY.SOFT_RESET_CONFIRM(cameraName)
            ) : (
              CAMERAS_COPY.HARD_RESET_CONFIRM(cameraName)
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {step === 1 ? (
          <div className="flex flex-col gap-4 py-2">
            <span className="text-xs font-semibold text-foreground uppercase tracking-wider">
              {CAMERAS_COPY.RESET_MODE_LABEL}
            </span>

            <RadioGroup
              value={mode}
              onValueChange={(val) => setMode(val as "Soft" | "Hard")}
              className="flex flex-col gap-2"
            >
              <div className="flex items-start gap-2 rounded-md border border-border p-2 transition-colors hover:bg-muted/30">
                <RadioGroupItem value="Soft" id="reset-mode-soft" className="mt-1" />
                <div className="flex flex-col gap-1">
                  <Label
                    htmlFor="reset-mode-soft"
                    className="text-sm font-semibold text-foreground leading-none cursor-pointer"
                  >
                    {CAMERAS_COPY.SOFT_RESET_TITLE}
                  </Label>
                  <span className="text-xs text-muted-foreground leading-relaxed">
                    {CAMERAS_COPY.SOFT_RESET_DESC(cameraName)}
                  </span>
                </div>
              </div>

              <div className="flex items-start gap-2 rounded-md border border-border p-2 transition-colors hover:bg-muted/30">
                <RadioGroupItem value="Hard" id="reset-mode-hard" className="mt-1" />
                <div className="flex flex-col gap-1">
                  <Label
                    htmlFor="reset-mode-hard"
                    className="text-sm font-semibold text-foreground leading-none cursor-pointer"
                  >
                    {CAMERAS_COPY.HARD_RESET_TITLE}
                  </Label>
                  <span className="text-xs text-muted-foreground leading-relaxed">
                    {CAMERAS_COPY.HARD_RESET_DESC(cameraName)}
                  </span>
                </div>
              </div>
            </RadioGroup>

            <p className="text-xs text-muted-foreground bg-muted/40 p-2 rounded border border-border/50">
              {selectedDesc}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4 py-2">
            <Field className="flex flex-col gap-1">
              <FieldLabel htmlFor="reset-confirm-input" className="text-xs font-semibold">
                {CAMERAS_COPY.TYPE_RESET_LABEL}
              </FieldLabel>
              <Input
                id="reset-confirm-input"
                autoComplete="off"
                placeholder="RESET"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                disabled={resetMutation.isPending}
                className="font-mono text-sm uppercase tracking-wider"
              />
              <FieldDescription className="text-xs text-muted-foreground">
                {CAMERAS_COPY.TYPE_RESET_HELPER}
              </FieldDescription>
            </Field>

            {hasError && (
              <InlineError
                message={CAMERAS_COPY.RESET_FAILED(cameraName)}
                actionLabel={CAMERAS_COPY.RETRY_RESET}
                onAction={handleReset}
                pending={resetMutation.isPending}
              />
            )}
          </div>
        )}

        <AlertDialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
          {step === 1 ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
              >
                {CAMERAS_COPY.KEEP_SETTINGS_BUTTON}
              </Button>
              <Button
                type="button"
                variant="default"
                onClick={() => setStep(2)}
              >
                {CAMERAS_COPY.CONTINUE_RESET_BUTTON}
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setStep(1);
                  setHasError(false);
                }}
                disabled={resetMutation.isPending}
              >
                {CAMERAS_COPY.BACK_TO_RESET_MODE}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={resetMutation.isPending}
              >
                {CAMERAS_COPY.KEEP_SETTINGS_BUTTON}
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleReset}
                disabled={!isConfirmed || resetMutation.isPending}
              >
                {resetMutation.isPending && (
                  <Spinner className="mr-2 h-4 w-4" />
                )}
                {mode === "Soft"
                  ? CAMERAS_COPY.SOFT_RESET_ACTION
                  : CAMERAS_COPY.HARD_RESET_ACTION}
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
