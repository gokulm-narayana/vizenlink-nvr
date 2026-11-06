import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PasswordField } from "@/components/PasswordField";
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { useResetUserPassword, type UserItem } from "./api";
import { USERS_COPY } from "./copy";

export interface ResetPasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserItem;
}

export const ResetPasswordDialog: React.FC<ResetPasswordDialogProps> = ({
  open,
  onOpenChange,
  user,
}) => {
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    newPassword?: string;
    confirmPassword?: string;
  }>({});
  const [generalError, setGeneralError] = useState<string | null>(null);

  const resetMutation = useResetUserPassword(user.id);

  useEffect(() => {
    if (open) {
      setNewPassword("");
      setConfirmPassword("");
      setFieldErrors({});
      setGeneralError(null);
    }
  }, [open, user]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setGeneralError(null);
    const errors: typeof fieldErrors = {};

    if (!newPassword) {
      errors.newPassword = USERS_COPY.PASSWORD_REQUIRED;
    } else if (newPassword.length < 8) {
      errors.newPassword = USERS_COPY.PASSWORD_TOO_SHORT;
    }

    if (newPassword !== confirmPassword) {
      errors.confirmPassword = USERS_COPY.PASSWORD_MISMATCH;
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      await resetMutation.mutateAsync({
        new_password: newPassword,
      });
      toast.success(USERS_COPY.PASSWORD_RESET_TOAST(user.username));
      onOpenChange(false);
    } catch {
      setGeneralError(USERS_COPY.RESET_PASSWORD_FAILED(user.username));
    }
  };

  const isPending = resetMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !isPending) {
          onOpenChange(false);
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{USERS_COPY.RESET_PASSWORD_TITLE(user.username)}</DialogTitle>
          <DialogDescription className="sr-only">
            Reset user password
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 py-2">
          {generalError && (
            <InlineError
              message={generalError}
              actionLabel={USERS_COPY.RETRY_RESET_PASSWORD}
              onAction={() => handleSubmit()}
              pending={isPending}
            />
          )}

          {/* New Password */}
          <Field className="flex flex-col gap-1">
            <FieldLabel htmlFor="reset-new-password" className="text-xs font-semibold">
              {USERS_COPY.NEW_PASSWORD_LABEL}
            </FieldLabel>
            <PasswordField
              id="reset-new-password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value);
                if (fieldErrors.newPassword) {
                  setFieldErrors((prev) => ({ ...prev, newPassword: undefined }));
                }
              }}
              disabled={isPending}
              className="text-sm font-normal"
            />
            {fieldErrors.newPassword ? (
              <FieldError>{fieldErrors.newPassword}</FieldError>
            ) : (
              <FieldDescription className="text-xs text-muted-foreground">
                {USERS_COPY.RESET_PASSWORD_HELPER(user.username)}
              </FieldDescription>
            )}
          </Field>

          {/* Confirm Password */}
          <Field className="flex flex-col gap-1">
            <FieldLabel htmlFor="reset-confirm-password" className="text-xs font-semibold">
              {USERS_COPY.CONFIRM_PASSWORD_LABEL}
            </FieldLabel>
            <PasswordField
              id="reset-confirm-password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                if (fieldErrors.confirmPassword) {
                  setFieldErrors((prev) => ({ ...prev, confirmPassword: undefined }));
                }
              }}
              disabled={isPending}
              className="text-sm font-normal"
            />
            {fieldErrors.confirmPassword && (
              <FieldError>{fieldErrors.confirmPassword}</FieldError>
            )}
          </Field>

          <DialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
              className="text-xs"
            >
              {USERS_COPY.KEEP_CURRENT_PASSWORD}
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={isPending}
              className="text-xs"
            >
              {isPending && <Spinner className="mr-2 h-4 w-4" />}
              {USERS_COPY.RESET_PASSWORD_BUTTON}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
