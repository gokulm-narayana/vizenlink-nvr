import { useAccountPreferences } from "@/features/profile/preferences";
import React, { useState, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { toast } from "sonner";
import { User, Sun, Moon, Monitor, KeyRound, LogOut } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { InlineError } from "@/components/InlineError";
import { useCurrentUser, useCameras } from "@/lib/queries";
import { useUiStore, type Theme, type ViewMode } from "@/stores/ui";
import { useSignOut } from "@/features/auth/api";
import { useMe } from "./api";
import { ChangePasswordDialog } from "./ChangePasswordDialog";
import { ROLE_DESCRIPTIONS, PROFILE_COPY } from "./copy";

export const ProfilePage: React.FC = () => {
  const { setTheme, setViewMode } = useAccountPreferences();
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);
  const currentUser = useCurrentUser();
  const theme = useUiStore((s) => s.theme);
  const viewMode = useUiStore((s) => s.viewMode);
  const signOut = useSignOut();
  const signOutOthers = useMutation({
    mutationFn: () => apiFetch<{ revoked: number }>("/api/v1/auth/sessions/sign-out-others", { method: "POST" }),
    onSuccess: ({ revoked }) => toast.success(revoked ? "Other sessions signed out" : "No other sessions were open"),
    onError: error => toast.error(error.message),
  });

  const { data: me, isLoading: meLoading, error: meError, refetch: refetchMe } = useMe();
  const { data: cameras = [], isLoading: camerasLoading } = useCameras();

  const cameraMap = useMemo(() => {
    const map = new Map<string, string>();
    cameras.forEach((c) => {
      map.set(c.serial, c.name);
    });
    return map;
  }, [cameras]);

  const user = me || currentUser;
  const username = user?.username || "User";
  const role = user?.role || "viewer";
  const permissions = me?.permissions || currentUser?.permissions || [];
  const initial = username.charAt(0).toUpperCase() || "U";

  const isOwnerOrOperator = role === "owner" || role === "operator";

  if (meLoading && !user) {
    return (
      <div className="flex flex-col gap-6 min-h-full max-w-[640px]">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (meError && !user) {
    return (
      <div className="max-w-[640px]">
        <InlineError
          message={PROFILE_COPY.LOAD_ERROR}
          actionLabel={PROFILE_COPY.RELOAD_PROFILE}
          onAction={() => void refetchMe()}
        />
      </div>
    );
  }

  return (
    <div className="grid min-h-full max-w-[1280px] content-start items-start gap-6 xl:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-6">
      {/* 1. Account Card (Primary visual anchor) */}
      <Card className="border-border bg-card p-6 flex flex-col gap-6">
        <CardHeader className="p-0 pb-4 border-b border-border flex flex-row items-center gap-4">
          <Avatar className="h-16 w-16">
            <AvatarFallback className="bg-primary/10 text-primary text-xl font-semibold">
              {initial}
            </AvatarFallback>
          </Avatar>

          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xl font-semibold text-foreground tracking-tight truncate">
                {username}
              </span>
              <Badge variant="secondary" className="capitalize text-xs font-semibold">
                {role}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">
              {ROLE_DESCRIPTIONS[role] || "Watches the cameras you choose."}
            </span>
          </div>
        </CardHeader>

        <CardContent className="p-0 flex flex-col gap-2">
          <span className="text-xs font-semibold text-foreground">
            {PROFILE_COPY.CAMERAS_YOU_CAN_VIEW}
          </span>

          {isOwnerOrOperator ? (
            <span className="text-xs text-foreground font-semibold">
              {PROFILE_COPY.ALL_CAMERAS}
            </span>
          ) : permissions.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {permissions.map((serial) => (
                <Badge
                  key={serial}
                  variant="outline"
                  className="text-xs font-normal border-border bg-muted/40"
                >
                  {cameraMap.get(serial) || serial}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">
              {PROFILE_COPY.NO_CAMERAS_VIEWER}
            </span>
          )}
        </CardContent>
      </Card>

      {/* 2. Security Card */}
      <Card className="border-border bg-card p-6 flex flex-col gap-4">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            {PROFILE_COPY.SECURITY_TITLE}
          </CardTitle>
        </CardHeader>

        <CardContent className="p-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold text-foreground">Password</span>
            <span className="text-xs text-muted-foreground">
              {PROFILE_COPY.SECURITY_CAPTION}
            </span>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setIsChangePasswordOpen(true)}
            className="gap-2 text-xs shrink-0 h-8"
          >
            <KeyRound className="h-4 w-4" />
            <span>{PROFILE_COPY.CHANGE_PASSWORD_ACTION}</span>
          </Button>
        </CardContent>

        {/* Same row shape as Password: what it is on the left, the action on the right. */}
        <CardContent className="p-0 pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold text-foreground">Other sessions</span>
            <span className="text-xs text-muted-foreground">
              Sign out every other browser and device that is using this account.
            </span>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={signOutOthers.isPending}
            onClick={() => signOutOthers.mutate()}
            className="gap-2 text-xs shrink-0 h-8"
          >
            <LogOut className="h-4 w-4" />
            <span>Sign out other sessions</span>
          </Button>
        </CardContent>
      </Card>

      </div>

      {/* 3. Preferences Card */}
      <Card className="border-border bg-card p-6 flex flex-col gap-6">
        <CardHeader className="p-0 pb-2 border-b border-border">
          <CardTitle className="text-sm font-semibold text-foreground">
            {PROFILE_COPY.PREFERENCES_TITLE}
          </CardTitle>
        </CardHeader>

        <CardContent className="p-0 flex flex-col gap-6">
          {/* Theme Radio Group */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold text-foreground">Theme</label>
            <RadioGroup
              value={theme}
              onValueChange={(val) => setTheme(val as Theme)}
              className="grid grid-cols-3 gap-2"
            >
              <label
                htmlFor="theme-light"
                className="flex items-center gap-2 rounded-md border border-border p-2.5 text-xs font-semibold cursor-pointer hover:bg-muted/50 transition-colors has-data-checked:border-primary has-data-checked:bg-muted/30"
              >
                <RadioGroupItem value="light" id="theme-light" />
                <Sun className="h-4 w-4 text-foreground" />
                <span>Light</span>
              </label>

              <label
                htmlFor="theme-dark"
                className="flex items-center gap-2 rounded-md border border-border p-2.5 text-xs font-semibold cursor-pointer hover:bg-muted/50 transition-colors has-data-checked:border-primary has-data-checked:bg-muted/30"
              >
                <RadioGroupItem value="dark" id="theme-dark" />
                <Moon className="h-4 w-4 text-foreground" />
                <span>Dark</span>
              </label>

              <label
                htmlFor="theme-system"
                className="flex items-center gap-2 rounded-md border border-border p-2.5 text-xs font-semibold cursor-pointer hover:bg-muted/50 transition-colors has-data-checked:border-primary has-data-checked:bg-muted/30"
              >
                <RadioGroupItem value="system" id="theme-system" />
                <Monitor className="h-4 w-4 text-foreground" />
                <span>System</span>
              </label>
            </RadioGroup>
          </div>

          {/* View Mode Toggle Group */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold text-foreground">View Mode</label>
            <ToggleGroup
              type="single"
              value={viewMode}
              onValueChange={(val) => val && setViewMode(val as ViewMode)}
              className="w-full justify-start rounded-md border border-border bg-muted/40 p-1"
            >
              <ToggleGroupItem
                value="simple"
                className="flex-1 text-xs font-semibold data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-xs h-7"
              >
                Simple
              </ToggleGroupItem>
              <ToggleGroupItem
                value="advanced"
                className="flex-1 text-xs font-semibold data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-xs h-7"
              >
                Advanced
              </ToggleGroupItem>
            </ToggleGroup>
            <span className="text-xs text-muted-foreground">
              {PROFILE_COPY.PREFERENCES_CAPTION}
            </span>
          </div>

          {/* Sign Out Button in Footer */}
          <div className="pt-2 border-t border-border flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void signOut()}
              className="gap-2 text-xs h-8 text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
              <span>{PROFILE_COPY.SIGN_OUT}</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Change Password Dialog */}
      <ChangePasswordDialog
        open={isChangePasswordOpen}
        onOpenChange={setIsChangePasswordOpen}
      />
    </div>
  );
};
