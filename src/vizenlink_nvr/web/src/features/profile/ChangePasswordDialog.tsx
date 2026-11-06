import React, { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PasswordField } from "@/components/PasswordField";
import { InlineError } from "@/components/InlineError";
import { ApiError } from "@/lib/api";
import { useChangePassword } from "./api";
import { PROFILE_COPY } from "./copy";

export interface ChangePasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const ChangePasswordDialog: React.FC<ChangePasswordDialogProps> = ({
  open,
  onOpenChange,
}) => {
  const currentPasswordRef = useRef<HTMLInputElement>(null);
  const changePasswordMutation = useChangePassword();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [fieldErrors, setFieldErrors] = useState<{
    current?: string;
    new?: string;
    confirm?: string;
  }>({});
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setFieldErrors({});
      setGeneralError(null);
    }
  }, [open]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setGeneralError(null);
    const errors: typeof fieldErrors = {};

    if (!currentPassword) {
      errors.current = "Current password is required.";
    }

    if (newPassword.length < 8) {
      errors.new = PROFILE_COPY.PASSWORD_TOO_SHORT;
    }

    if (newPassword !== confirmPassword) {
      errors.confirm = PROFILE_COPY.PASSWORD_MISMATCH;
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});

    try {
      await changePasswordMutation.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      });

      toast(PROFILE_COPY.PASSWORD_CHANGED_TOAST);
      onOpenChange(false);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 400) {
        setFieldErrors({ current: PROFILE_COPY.WRONG_CURRENT_PASSWORD });
        currentPasswordRef.current?.focus();
      } else {
        setGeneralError(PROFILE_COPY.CHANGE_PASSWORD_FAILED);
      }
    }
  };

  const isSubmitting = changePasswordMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!isSubmitting) {
          onOpenChange(next);
        }
      }}
    >
      <DialogContent
        onPointerDownOutside={(e) => {
          if (isSubmitting) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (isSubmitting) e.preventDefault();
        }}
        className="max-w-[480px] p-0 overflow-hidden bg-card border-border"
      >
        <form onSubmit={handleSubmit} className="flex flex-col">
          <DialogHeader className="p-6 pb-4 border-b border-border">
            <DialogTitle className="text-sm font-semibold text-foreground">
              {PROFILE_COPY.CHANGE_PASSWORD_TITLE}
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              {PROFILE_COPY.SECURITY_CAPTION}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 p-6">
            {generalError && (
              <InlineError
                message={generalError}
                actionLabel={PROFILE_COPY.RETRY_CHANGE_PASSWORD}
                onAction={() => void handleSubmit()}
              />
            )}

            {/* Current Password */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="current-password"
                className="text-xs font-semibold text-foreground"
              >
                Current password
              </label>
              <PasswordField
                id="current-password"
                ref={currentPasswordRef}
                value={currentPassword}
                onChange={(e) => {
                  setCurrentPassword(e.target.value);
                  setFieldErrors((prev) => ({ ...prev, current: undefined }));
                }}
                disabled={isSubmitting}
                autoComplete="current-password"
                className="text-xs"
              />
              {fieldErrors.current && (
                <span className="text-xs text-critical">
                  {fieldErrors.current}
                </span>
              )}
            </div>

            {/* New Password */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="new-password"
                className="text-xs font-semibold text-foreground"
              >
                New password
              </label>
              <PasswordField
                id="new-password"
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  setFieldErrors((prev) => ({ ...prev, new: undefined }));
                }}
                disabled={isSubmitting}
                autoComplete="new-password"
                className="text-xs"
              />
              <span className="text-xs text-muted-foreground">
                {PROFILE_COPY.NEW_PASSWORD_HELPER}
              </span>
              {fieldErrors.new && (
                <span className="text-xs text-critical">
                  {fieldErrors.new}
                </span>
              )}
            </div>

            {/* Confirm New Password */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="confirm-password"
                className="text-xs font-semibold text-foreground"
              >
                Confirm new password
              </label>
              <PasswordField
                id="confirm-password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setFieldErrors((prev) => ({ ...prev, confirm: undefined }));
                }}
                disabled={isSubmitting}
                autoComplete="new-password"
                className="text-xs"
              />
              {fieldErrors.confirm && (
                <span className="text-xs text-critical">
                  {fieldErrors.confirm}
                </span>
              )}
            </div>
          </div>

          <DialogFooter className="border-t border-border p-4 bg-card gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
              className="text-xs h-8"
            >
              {PROFILE_COPY.KEEP_PASSWORD_ACTION}
            </Button>
            <Button
              type="submit"
              variant="default"
              size="sm"
              disabled={isSubmitting}
              className="text-xs h-8"
            >
              {isSubmitting && (
                <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
              )}
              {PROFILE_COPY.CHANGE_PASSWORD_ACTION}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
