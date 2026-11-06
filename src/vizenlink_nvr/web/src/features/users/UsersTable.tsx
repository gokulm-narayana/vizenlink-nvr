import React from "react";
import { EllipsisVertical, TriangleAlert } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/StatusBadge";
import { useSiteTimeZone, formatDateTime } from "@/lib/time";
import type { UserItem } from "./api";
import { USERS_COPY } from "./copy";

export interface UsersTableProps {
  users: UserItem[];
  currentUserId?: number;
  onEditAccess: (user: UserItem) => void;
  onDisableUser: (user: UserItem) => void;
  onEnableUser: (user: UserItem) => void;
  onResetPassword: (user: UserItem) => void;
  onChangeOwnPassword: () => void;
}

export const UsersTable: React.FC<UsersTableProps> = ({
  users,
  currentUserId,
  onEditAccess,
  onDisableUser,
  onEnableUser,
  onResetPassword,
  onChangeOwnPassword,
}) => {
  const siteZone = useSiteTimeZone();

  const renderCamerasCell = (user: UserItem) => {
    if (user.role === "owner" || user.role === "operator") {
      return (
        <span className="text-xs text-muted-foreground">
          {USERS_COPY.ALL_CAMERAS}
        </span>
      );
    }

    const count = user.permissions?.length || 0;
    if (count > 0) {
      return (
        <span className="text-xs text-foreground font-normal">
          {USERS_COPY.CAMERAS_COUNT(count)}
        </span>
      );
    }

    return (
      <span
        className="inline-flex items-center gap-1 text-xs text-warning"
        title={USERS_COPY.NO_CAMERAS_TITLE}
      >
        <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
        {USERS_COPY.NO_CAMERAS}
      </span>
    );
  };

  const renderActionsMenu = (user: UserItem) => {
    const isOwnRow = user.id === currentUserId;

    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label={USERS_COPY.ACTIONS_LABEL(user.username)}
          >
            <EllipsisVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => onEditAccess(user)}>
            {USERS_COPY.ACTION_EDIT_ACCESS}
          </DropdownMenuItem>

          {user.is_active ? (
            isOwnRow ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <DropdownMenuItem
                      disabled
                      className="opacity-50 cursor-not-allowed"
                    >
                      {USERS_COPY.ACTION_DISABLE_USER}
                    </DropdownMenuItem>
                  </div>
                </TooltipTrigger>
                <TooltipContent>{USERS_COPY.CANNOT_DISABLE_SELF}</TooltipContent>
              </Tooltip>
            ) : (
              <DropdownMenuItem
                onClick={() => onDisableUser(user)}
                className="text-critical focus:text-critical"
              >
                {USERS_COPY.ACTION_DISABLE_USER}
              </DropdownMenuItem>
            )
          ) : (
            <DropdownMenuItem onClick={() => onEnableUser(user)}>
              {USERS_COPY.ACTION_ENABLE_USER}
            </DropdownMenuItem>
          )}

          {isOwnRow ? (
            <DropdownMenuItem onClick={onChangeOwnPassword}>
              {USERS_COPY.ACTION_CHANGE_PASSWORD}
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={() => onResetPassword(user)}>
              {USERS_COPY.ACTION_RESET_PASSWORD}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  return (
    <>
      {/* Desktop Table View (>= 768px) */}
      <div className="hidden md:block rounded-lg border border-border bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs font-semibold">
                {USERS_COPY.COL_USERNAME}
              </TableHead>
              <TableHead className="text-xs font-semibold">
                {USERS_COPY.COL_ROLE}
              </TableHead>
              <TableHead className="text-xs font-semibold">
                {USERS_COPY.COL_STATUS}
              </TableHead>
              <TableHead className="text-xs font-semibold">
                {USERS_COPY.COL_CAMERAS}
              </TableHead>
              <TableHead className="text-xs font-semibold">
                {USERS_COPY.COL_CREATED}
              </TableHead>
              <TableHead className="w-12 text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => {
              const isOwnRow = user.id === currentUserId;
              const formattedDate = formatDateTime(user.created_at, siteZone, {
                month: "short",
                day: "numeric",
                year: "numeric",
              });

              return (
                <TableRow key={user.id}>
                  {/* Username */}
                  <TableCell className="text-sm font-semibold text-foreground">
                    <div className="flex items-center gap-2">
                      <span>{user.username}</span>
                      {isOwnRow && (
                        <Badge
                          variant="secondary"
                          className="text-xs font-normal px-1.5 py-0"
                        >
                          {USERS_COPY.YOU_BADGE}
                        </Badge>
                      )}
                    </div>
                  </TableCell>

                  {/* Role */}
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className="capitalize text-xs font-normal"
                    >
                      {user.role}
                    </Badge>
                  </TableCell>

                  {/* Status */}
                  <TableCell>
                    <StatusBadge
                      kind={user.is_active ? "user-active" : "user-disabled"}
                    />
                  </TableCell>

                  {/* Cameras */}
                  <TableCell>{renderCamerasCell(user)}</TableCell>

                  {/* Created */}
                  <TableCell className="text-xs text-muted-foreground">
                    {formattedDate}
                  </TableCell>

                  {/* Actions */}
                  <TableCell className="text-right">
                    {renderActionsMenu(user)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Mobile Stacked Card View (< 768px) */}
      <div className="flex flex-col gap-4 md:hidden">
        {users.map((user) => {
          const isOwnRow = user.id === currentUserId;
          const formattedDate = formatDateTime(user.created_at, siteZone, {
            month: "short",
            day: "numeric",
            year: "numeric",
          });

          return (
            <div
              key={user.id}
              className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    {user.username}
                  </span>
                  {isOwnRow && (
                    <Badge
                      variant="secondary"
                      className="text-xs font-normal px-1.5 py-0"
                    >
                      {USERS_COPY.YOU_BADGE}
                    </Badge>
                  )}
                </div>
                {renderActionsMenu(user)}
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/50">
                <Badge
                  variant="secondary"
                  className="capitalize text-xs font-normal"
                >
                  {user.role}
                </Badge>
                <StatusBadge
                  kind={user.is_active ? "user-active" : "user-disabled"}
                />
              </div>

              <div className="flex items-center justify-between gap-2 text-xs pt-1">
                <div>{renderCamerasCell(user)}</div>
                <span className="text-muted-foreground">{formattedDate}</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
};
