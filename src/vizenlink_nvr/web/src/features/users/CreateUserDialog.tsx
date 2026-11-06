import React, { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/field";
import { PasswordField } from "@/components/PasswordField";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { CameraChecklist } from "./CameraChecklist";
import { useCreateUser } from "./api";
import { USERS_COPY } from "./copy";
import { ROLE_DESCRIPTIONS } from "@/features/profile/copy";
import { ApiError } from "@/lib/api";

export interface CreateUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const CreateUserDialog: React.FC<CreateUserDialogProps> = ({
  open,
  onOpenChange,
}) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"viewer" | "operator" | "owner">("viewer");
  const [permissions, setPermissions] = useState<string[]>([]);

  const [fieldErrors, setFieldErrors] = useState<{
    username?: string;
    password?: string;
    confirmPassword?: string;
  }>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  const createMutation = useCreateUser();

  const isDirty = Boolean(
    username.trim() || password || confirmPassword || permissions.length > 0
  );

  const resetForm = () => {
    setUsername("");
    setPassword("");
    setConfirmPassword("");
    setRole("viewer");
    setPermissions([]);
    setFieldErrors({});
    setGeneralError(null);
    setShowDiscardConfirm(false);
  };

  const handleClose = () => {
    if (isDirty) {
      setShowDiscardConfirm(true);
    } else {
      resetForm();
      onOpenChange(false);
    }
  };

  const handleConfirmDiscard = () => {
    resetForm();
    onOpenChange(false);
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setGeneralError(null);
    const errors: typeof fieldErrors = {};

    const cleanUsername = username.trim();
    if (!cleanUsername) {
      errors.username = USERS_COPY.USERNAME_REQUIRED;
    }

    if (!password) {
      errors.password = USERS_COPY.PASSWORD_REQUIRED;
    } else if (password.length < 8) {
      errors.password = USERS_COPY.PASSWORD_TOO_SHORT;
    }

    if (password !== confirmPassword) {
      errors.confirmPassword = USERS_COPY.PASSWORD_MISMATCH;
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      await createMutation.mutateAsync({
        username: cleanUsername,
        password,
        role,
        permissions: role === "viewer" ? permissions : [],
      });
      toast.success(USERS_COPY.USER_CREATED_TOAST);
      resetForm();
      onOpenChange(false);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setFieldErrors({
          username: USERS_COPY.USERNAME_TAKEN(cleanUsername),
        });
      } else {
        setGeneralError(USERS_COPY.CREATE_FAILED(cleanUsername));
      }
    }
  };

  const isPending = createMutation.isPending;

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next && !isPending) {
            handleClose();
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{USERS_COPY.CREATE_TITLE}</DialogTitle>
            <DialogDescription className="sr-only">
              Create a new user account with role and optional camera whitelist
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4 py-2">
            {generalError && (
              <InlineError
                message={generalError}
                actionLabel={USERS_COPY.RETRY_CREATE}
                onAction={() => handleSubmit()}
                pending={isPending}
              />
            )}

            {/* Username */}
            <Field className="flex flex-col gap-1">
              <FieldLabel htmlFor="create-username" className="text-xs font-semibold">
                {USERS_COPY.USERNAME_LABEL}
              </FieldLabel>
              <Input
                id="create-username"
                autoComplete="off"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  if (fieldErrors.username) {
                    setFieldErrors((prev) => ({ ...prev, username: undefined }));
                  }
                }}
                disabled={isPending}
                className="text-sm font-normal"
              />
              {fieldErrors.username && (
                <FieldError>{fieldErrors.username}</FieldError>
              )}
            </Field>

            {/* Password */}
            <Field className="flex flex-col gap-1">
              <FieldLabel htmlFor="create-password" className="text-xs font-semibold">
                {USERS_COPY.PASSWORD_LABEL}
              </FieldLabel>
              <PasswordField
                id="create-password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (fieldErrors.password) {
                    setFieldErrors((prev) => ({ ...prev, password: undefined }));
                  }
                }}
                disabled={isPending}
                className="text-sm font-normal"
              />
              {fieldErrors.password ? (
                <FieldError>{fieldErrors.password}</FieldError>
              ) : (
                <FieldDescription className="text-xs text-muted-foreground">
                  {USERS_COPY.PASSWORD_HELPER}
                </FieldDescription>
              )}
            </Field>

            {/* Confirm Password */}
            <Field className="flex flex-col gap-1">
              <FieldLabel htmlFor="create-confirm-password" className="text-xs font-semibold">
                {USERS_COPY.CONFIRM_PASSWORD_LABEL}
              </FieldLabel>
              <PasswordField
                id="create-confirm-password"
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

            {/* Role Radio Group */}
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-foreground">
                {USERS_COPY.ROLE_LABEL}
              </span>
              <RadioGroup
                value={role}
                onValueChange={(val) => setRole(val as "viewer" | "operator" | "owner")}
                disabled={isPending}
                className="flex flex-col gap-2"
              >
                {(["viewer", "operator", "owner"] as const).map((r) => (
                  <div
                    key={r}
                    className="flex items-start gap-2 rounded-md border border-border p-2 transition-colors hover:bg-muted/30"
                  >
                    <RadioGroupItem value={r} id={`role-${r}`} className="mt-0.5" />
                    <div className="flex flex-col gap-0.5">
                      <Label
                        htmlFor={`role-${r}`}
                        className="text-xs font-semibold text-foreground capitalize cursor-pointer"
                      >
                        {r}
                      </Label>
                      <span className="text-xs text-muted-foreground leading-relaxed">
                        {ROLE_DESCRIPTIONS[r]}
                      </span>
                    </div>
                  </div>
                ))}
              </RadioGroup>
            </div>

            {/* Camera Checklist (only for Viewer role) */}
            {role === "viewer" && (
              <div className="pt-2 border-t border-border">
                <CameraChecklist
                  selectedSerials={permissions}
                  onChange={setPermissions}
                  disabled={isPending}
                />
              </div>
            )}

            <DialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={isPending}
                className="text-xs"
              >
                {USERS_COPY.DISCARD_NEW_USER}
              </Button>
              <Button
                type="submit"
                variant="default"
                disabled={isPending}
                className="text-xs"
              >
                {isPending && <Spinner className="mr-2 h-4 w-4" />}
                {USERS_COPY.CREATE_USER_BUTTON}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Discard Confirmation Alert Dialog */}
      <AlertDialog
        open={showDiscardConfirm}
        onOpenChange={(openNext) => {
          if (!openNext) setShowDiscardConfirm(false);
        }}
      >
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{USERS_COPY.DISCARD_DIALOG_TITLE}</AlertDialogTitle>
            <AlertDialogDescription>
              {USERS_COPY.DISCARD_DIALOG_BODY}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowDiscardConfirm(false)}
            >
              {USERS_COPY.KEEP_EDITING_USER}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirmDiscard}
            >
              {USERS_COPY.DISCARD_NEW_USER}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
