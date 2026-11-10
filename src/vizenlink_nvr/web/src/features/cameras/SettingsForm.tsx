import React from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { OctagonAlert, Loader2 } from "lucide-react";
import { CAMERAS_COPY } from "./copy";

export interface SettingsFormProps {
  isDirty: boolean;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  onDiscard: () => void;
  onSubmit: (e?: React.FormEvent) => void;
  retryLabel?: string;
  children: React.ReactNode;
}

export const SettingsForm: React.FC<SettingsFormProps> = ({
  isDirty,
  isSubmitting = false,
  errorMessage,
  onDiscard,
  onSubmit,
  retryLabel = CAMERAS_COPY.RETRY_SAVE,
  children,
}) => {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(e);
      }}
      className="flex flex-col flex-1"
    >
      <div className="flex-1 flex flex-col gap-6">{children}</div>

      {/* Error alert above footer */}
      {errorMessage && (
        <Alert variant="destructive" role="alert" className="mt-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <OctagonAlert className="h-4 w-4 shrink-0 text-critical" />
            <AlertDescription className="text-xs">{errorMessage}</AlertDescription>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onSubmit()}
            disabled={isSubmitting}
            className="shrink-0 text-xs"
          >
            {retryLabel}
          </Button>
        </Alert>
      )}

      {/* Sticky footer only when dirty or submitting or error */}
      {(isDirty || isSubmitting || errorMessage) && (
        <div className="sticky bottom-0 -mx-6 -mb-6 mt-6 flex items-center justify-end gap-2 border-t border-border bg-card/95 p-4 backdrop-blur-xs z-10">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDiscard}
            disabled={isSubmitting}
          >
            {CAMERAS_COPY.DISCARD_CHANGES}
          </Button>
          <Button
            type="submit"
            variant="default"
            size="sm"
            disabled={isSubmitting}
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
            {CAMERAS_COPY.SAVE_CHANGES}
          </Button>
        </div>
      )}
    </form>
  );
};