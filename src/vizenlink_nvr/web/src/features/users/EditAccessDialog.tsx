import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CameraChecklist } from "./CameraChecklist";
import { useUpdateUser, type UserItem } from "./api";
import { USERS_COPY } from "./copy";
import { ROLE_DESCRIPTIONS } from "@/features/profile/copy";
import { ApiError } from "@/lib/api";

export interface EditAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserItem;
  isOwnRow?: boolean;
}

export const EditAccessDialog: React.FC<EditAccessDialogProps> = ({
  open,
  onOpenChange,
  user,
  isOwnRow = false,
}) => {
  const [role, setRole] = useState<"viewer" | "operator" | "owner">(user.role);
  const [permissions, setPermissions] = useState<string[]>(user.permissions || []);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isStaleCameras, setIsStaleCameras] = useState<boolean>(false);

  const queryClient = useQueryClient();
  const updateMutation = useUpdateUser(user.id);

  useEffect(() => {
    if (open) {
      setRole(user.role);
      setPermissions(user.permissions || []);
      setErrorMessage(null);
      setIsStaleCameras(false);
    }
  }, [open, user]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setErrorMessage(null);
    setIsStaleCameras(false);

    try {
      const payload: { role?: string; permissions?: string[] } = {
        role,
      };

      if (role === "viewer") {
        payload.permissions = permissions;
      }

      await updateMutation.mutateAsync(payload);
      toast.success(USERS_COPY.ACCESS_SAVED_TOAST(user.username));
      onOpenChange(false);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 400 && err.detail.includes("Unknown camera")) {
        setIsStaleCameras(true);
        setErrorMessage(USERS_COPY.STALE_CAMERAS_ERROR);
      } else {
        setErrorMessage(USERS_COPY.SAVE_ACCESS_FAILED(user.username));
      }
    }
  };

  const handleReloadCameras = () => {
    queryClient.invalidateQueries({ queryKey: ["cameras"] });
    setErrorMessage(null);
    setIsStaleCameras(false);
  };

  const isPending = updateMutation.isPending;

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
          <DialogTitle>{USERS_COPY.EDIT_ACCESS_TITLE(user.username)}</DialogTitle>
          <DialogDescription className="sr-only">
            Edit user role and camera permissions
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 py-2">
          {errorMessage && (
            <InlineError
              message={errorMessage}
              actionLabel={
                isStaleCameras
                  ? USERS_COPY.RELOAD_CAMERAS
                  : USERS_COPY.RETRY_SAVE_ACCESS
              }
              onAction={isStaleCameras ? handleReloadCameras : () => handleSubmit()}
              pending={isPending}
            />
          )}

          {/* Role selection */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold text-foreground">
              {USERS_COPY.ROLE_LABEL}
            </span>

            {isOwnRow ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    tabIndex={0}
                    className="opacity-60 cursor-not-allowed"
                    aria-disabled="true"
                  >
                    <RadioGroup
                      value={role}
                      disabled={true}
                      className="flex flex-col gap-2"
                    >
                      {(["viewer", "operator", "owner"] as const).map((r) => (
                        <div
                          key={r}
                          className="flex items-start gap-2 rounded-md border border-border p-2 bg-muted/20"
                        >
                          <RadioGroupItem
                            value={r}
                            id={`edit-role-${r}`}
                            disabled={true}
                            className="mt-0.5"
                          />
                          <div className="flex flex-col gap-0.5">
                            <span className="text-xs font-semibold text-foreground capitalize">
                              {r}
                            </span>
                            <span className="text-xs text-muted-foreground leading-relaxed">
                              {ROLE_DESCRIPTIONS[r]}
                            </span>
                          </div>
                        </div>
                      ))}
                    </RadioGroup>
                  </div>
                </TooltipTrigger>
                <TooltipContent>{USERS_COPY.CANNOT_CHANGE_OWN_ROLE}</TooltipContent>
              </Tooltip>
            ) : (
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
                    <RadioGroupItem value={r} id={`edit-role-${r}`} className="mt-0.5" />
                    <div className="flex flex-col gap-0.5">
                      <Label
                        htmlFor={`edit-role-${r}`}
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
            )}
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
              onClick={() => onOpenChange(false)}
              disabled={isPending}
              className="text-xs"
            >
              {USERS_COPY.DISCARD_ACCESS_CHANGES}
            </Button>
            <Button
              type="submit"
              variant="default"
              disabled={isPending}
              className="text-xs"
            >
              {isPending && <Spinner className="mr-2 h-4 w-4" />}
              {USERS_COPY.SAVE_ACCESS_BUTTON}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
