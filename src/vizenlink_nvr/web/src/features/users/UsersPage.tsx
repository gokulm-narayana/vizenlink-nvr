import React, { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { Forbidden } from "@/app/routes";
import { useCurrentUser } from "@/lib/queries";
import { ChangePasswordDialog } from "@/features/profile/ChangePasswordDialog";
import { useUsers, useUpdateUser, type UserItem } from "./api";
import { UsersTable } from "./UsersTable";
import { CreateUserDialog } from "./CreateUserDialog";
import { EditAccessDialog } from "./EditAccessDialog";
import { ResetPasswordDialog } from "./ResetPasswordDialog";
import { USERS_COPY } from "./copy";

export const UsersPage: React.FC = () => {
  const currentUser = useCurrentUser();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [resettingUser, setResettingUser] = useState<UserItem | null>(null);
  const [disablingUser, setDisablingUser] = useState<UserItem | null>(null);
  const [isDisablingPending, setIsDisablingPending] = useState(false);
  const [isChangeOwnPasswordOpen, setIsChangeOwnPasswordOpen] = useState(false);

  const [actionError, setActionError] = useState<{
    message: string;
    actionLabel: typeof USERS_COPY.RETRY_ENABLE | typeof USERS_COPY.RETRY_DISABLE;
    onAction: () => void;
  } | null>(null);

  const { data: users = [], isLoading, error: loadError, refetch } = useUsers();
  const updateMutation = useUpdateUser();

  if (currentUser && currentUser.role !== "owner") {
    return <Forbidden />;
  }

  const handleEnableUser = async (user: UserItem) => {
    setActionError(null);
    try {
      await updateMutation.mutateAsync({ id: user.id, is_active: true });
      toast.success(USERS_COPY.ENABLED_TOAST(user.username));
    } catch {
      setActionError({
        message: USERS_COPY.ENABLE_FAILED(user.username),
        actionLabel: USERS_COPY.RETRY_ENABLE,
        onAction: () => void handleEnableUser(user),
      });
    }
  };

  const handleConfirmDisable = async () => {
    if (!disablingUser) return;
    const target = disablingUser;
    setActionError(null);
    setIsDisablingPending(true);
    try {
      await updateMutation.mutateAsync({ id: target.id, is_active: false });
      toast.success(USERS_COPY.DISABLED_TOAST(target.username));
      setDisablingUser(null);
    } catch {
      setDisablingUser(null);
      setActionError({
        message: USERS_COPY.DISABLE_FAILED(target.username),
        actionLabel: USERS_COPY.RETRY_DISABLE,
        onAction: () => void handleDirectRetryDisable(target),
      });
    } finally {
      setIsDisablingPending(false);
    }
  };

  const handleDirectRetryDisable = async (target: UserItem) => {
    setActionError(null);
    try {
      await updateMutation.mutateAsync({ id: target.id, is_active: false });
      toast.success(USERS_COPY.DISABLED_TOAST(target.username));
    } catch {
      setActionError({
        message: USERS_COPY.DISABLE_FAILED(target.username),
        actionLabel: USERS_COPY.RETRY_DISABLE,
        onAction: () => void handleDirectRetryDisable(target),
      });
    }
  };

  return (
    <div className="flex flex-col gap-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold text-foreground tracking-tight">
          {USERS_COPY.TITLE}
        </h1>

        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={() => setIsCreateOpen(true)}
          className="gap-2 text-xs"
        >
          <Plus className="h-4 w-4" />
          <span>{USERS_COPY.CREATE_USER_BUTTON}</span>
        </Button>
      </div>

      {/* Action Error (Enable / Disable failure) */}
      {actionError && (
        <InlineError
          message={actionError.message}
          actionLabel={actionError.actionLabel}
          onAction={actionError.onAction}
        />
      )}

      {/* Load Error */}
      {loadError && (
        <InlineError
          message={USERS_COPY.LOAD_ERROR}
          actionLabel={USERS_COPY.RELOAD_USERS}
          onAction={() => void refetch()}
        />
      )}

      {/* Loading Skeleton */}
      {isLoading ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : users.length === 0 ? (
        /* Empty State */
        <div className="flex items-center justify-center py-12">
          <Empty className="py-12 border border-border max-w-lg">
            <EmptyHeader>
              <EmptyTitle>{USERS_COPY.EMPTY_HEADING}</EmptyTitle>
              <EmptyDescription>{USERS_COPY.EMPTY_BODY}</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={() => setIsCreateOpen(true)}
              >
                {USERS_COPY.CREATE_USER_BUTTON}
              </Button>
            </EmptyContent>
          </Empty>
        </div>
      ) : (
        <UsersTable
          users={users}
          currentUserId={currentUser?.id}
          onEditAccess={(user) => setEditingUser(user)}
          onDisableUser={(user) => setDisablingUser(user)}
          onEnableUser={(user) => void handleEnableUser(user)}
          onResetPassword={(user) => setResettingUser(user)}
          onChangeOwnPassword={() => setIsChangeOwnPasswordOpen(true)}
        />
      )}

      {/* Create User Dialog */}
      <CreateUserDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
      />

      {/* Edit Access Dialog */}
      {editingUser && (
        <EditAccessDialog
          open={Boolean(editingUser)}
          onOpenChange={(open) => !open && setEditingUser(null)}
          user={editingUser}
          isOwnRow={editingUser.id === currentUser?.id}
        />
      )}

      {/* Reset Password Dialog */}
      {resettingUser && (
        <ResetPasswordDialog
          open={Boolean(resettingUser)}
          onOpenChange={(open) => !open && setResettingUser(null)}
          user={resettingUser}
        />
      )}

      {/* Change Password Dialog (Own Row) */}
      <ChangePasswordDialog
        open={isChangeOwnPasswordOpen}
        onOpenChange={setIsChangeOwnPasswordOpen}
      />

      {/* Disable User Confirmation Dialog */}
      <AlertDialog
        open={Boolean(disablingUser)}
        onOpenChange={(open) => {
          if (!open && !isDisablingPending) setDisablingUser(null);
        }}
      >
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {disablingUser && USERS_COPY.DISABLE_TITLE(disablingUser.username)}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {disablingUser && USERS_COPY.DISABLE_DESCRIPTION(disablingUser.username)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={isDisablingPending}
              onClick={() => setDisablingUser(null)}
            >
              {USERS_COPY.KEEP_ENABLED_BUTTON}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="text-destructive hover:text-destructive border-destructive/30"
              disabled={isDisablingPending}
              onClick={handleConfirmDisable}
            >
              {isDisablingPending && <Spinner className="mr-2 h-4 w-4" />}
              {USERS_COPY.DISABLE_BUTTON}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
