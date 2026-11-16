import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search, Cctv, Radar, Plus } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useCameras, type CameraInfo } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { PasswordField } from "@/components/PasswordField";

type FoundCamera = { host: string; port: number; name: string; location: string; model: string };
const NEEDS_NEW_PASSWORD_MSG = "Set a new password on the camera before adding it.";

export function DiscoverCameras({ onAdded }: { onAdded: (camera: CameraInfo) => void }) {
  const { data: existing = [] } = useCameras();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<FoundCamera | null>(null);
  const [quickHost, setQuickHost] = useState("");
  const [quickPort, setQuickPort] = useState("443");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [passwordRuleError, setPasswordRuleError] = useState<string | null>(null);

  const resetDialogState = () => {
    setUsername("admin");
    setPassword("");
    setNeedsNewPassword(false);
    setNewPassword("");
    setConfirmNewPassword("");
    setPasswordRuleError(null);
    onboard.reset();
  };

  const scan = useMutation({ mutationFn: () => apiFetch<{ cameras: FoundCamera[] }>("/api/v1/cameras/discover", { method: "POST" }) });
  const onboard = useMutation({
    gcTime: 0,
    mutationFn: (credentials: {
      host: string;
      port: number;
      username: string;
      password: string;
      new_camera_password?: string;
    }) => apiFetch<CameraInfo>("/api/v1/cameras/onboard", { method: "POST", body: credentials }),
    onSuccess: (camera, variables) => {
      if (variables.new_camera_password) {
        toast.success("Use this new password in the VizenLink mobile app too.");
      }
      setPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setNeedsNewPassword(false);
      setPasswordRuleError(null);
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: ["cameras"] });
      onAdded(camera);
    },
    onError: (err) => {
      if (err.message === NEEDS_NEW_PASSWORD_MSG) {
        setNeedsNewPassword(true);
        setPasswordRuleError(null);
      }
    },
  });

  const handleQuickConnect = () => {
    const trimmed = quickHost.trim();
    if (!trimmed) return;
    const parsedPort = Number.parseInt(quickPort, 10);
    const port = Number.isFinite(parsedPort) && parsedPort >= 1 && parsedPort <= 65535 ? parsedPort : 443;
    resetDialogState();
    setSelected({
      host: trimmed,
      port,
      name: trimmed,
      location: "",
      model: "VizenLink / ONVIF",
    });
  };

  return (
    <section className="flex w-full flex-col gap-4 rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-2">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Radar className="size-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-foreground">Find cameras nearby</h2>
              <Badge variant="secondary" className="text-xs font-semibold">
                Auto-detect
              </Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Search for supported cameras on the recorder&apos;s network. Serial &amp; streams are read automatically.
            </p>
          </div>
        </div>
        <Button type="button" variant="default" size="sm" disabled={scan.isPending} onClick={() => scan.mutate()}>
          <Search className="size-4" />
          {scan.isPending ? "Searching…" : "Find cameras"}
        </Button>
      </div>

      {scan.isPending && (
        <p className="rounded-lg border border-border bg-muted/20 p-4 text-xs text-muted-foreground" role="status">
          Searching can take up to 30 seconds. You can also connect by IP below or enter details manually.
        </p>
      )}
      {scan.isError && <p role="alert" className="text-sm text-critical">{scan.error.message}</p>}
      {scan.data && !scan.isPending && (
        <div className="max-h-72 overflow-auto rounded-lg border border-border bg-background/40" aria-live="polite">
          {scan.data.cameras.length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground">
              No supported cameras found. Check that the camera and recorder are on the same network, connect by IP below, or enter its address manually.
            </p>
          ) : (
            scan.data.cameras.map((c) => {
              const added = existing.some((e) => e.host === c.host && (e.https_port || 443) === c.port);
              return (
                <div
                  key={`${c.host}:${c.port}`}
                  className="flex items-center gap-4 border-b border-border p-4 last:border-b-0"
                >
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Cctv className="size-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-foreground">{c.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {c.host}:{c.port} · {c.model}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant={added ? "ghost" : "outline"}
                    size="sm"
                    disabled={added}
                    onClick={() => {
                      resetDialogState();
                      setSelected(c);
                    }}
                  >
                    {added ? "Already added" : "Use camera"}
                  </Button>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Quick Connect by IP (auto ONVIF/NuraEye onboarding without manual stream fields) */}
      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <span className="text-xs font-semibold text-foreground">Quick connect by IP address</span>
        <p className="text-xs text-muted-foreground">
          Know the camera&apos;s local IP? Connect directly to auto-read its serial and video profiles.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            aria-label="Quick connect IP address"
            placeholder="e.g. 192.168.1.100"
            value={quickHost}
            onChange={(e) => setQuickHost(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleQuickConnect();
              }
            }}
            className="min-w-40 flex-1 text-sm"
          />
          <Input
            aria-label="Quick connect port"
            type="number"
            min={1}
            max={65535}
            value={quickPort}
            onChange={(e) => setQuickPort(e.target.value)}
            className="w-20 text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!quickHost.trim()}
            onClick={handleQuickConnect}
          >
            <Plus className="size-4" />
            Connect
          </Button>
        </div>
      </div>

      <Dialog open={selected !== null} onOpenChange={(open) => {
        if (open || onboard.isPending) return;
        setSelected(null);
        resetDialogState();
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add {selected?.name}</DialogTitle>
            <DialogDescription>Enter the camera’s credentials. The recorder will read its serial number and video streams automatically.</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!selected || !username.trim() || !password || onboard.isPending) return;
            if (needsNewPassword) {
              if (newPassword.length < 8 || newPassword.length > 32) {
                setPasswordRuleError("Use 8 to 32 characters.");
                return;
              }
              if (newPassword.toLowerCase() === "password") {
                setPasswordRuleError("Choose a password other than the factory password.");
                return;
              }
              if (newPassword !== confirmNewPassword) {
                setPasswordRuleError("New passwords do not match.");
                return;
              }
              setPasswordRuleError(null);
              onboard.mutate({
                host: selected.host,
                port: selected.port,
                username: username.trim(),
                password,
                new_camera_password: newPassword,
              });
              return;
            }
            onboard.mutate({ host: selected.host, port: selected.port, username: username.trim(), password });
          }}>
            <label className="vms-field">Camera username<Input value={username} maxLength={128} onChange={(event) => setUsername(event.target.value)} autoComplete="off" disabled={onboard.isPending} required /></label>
            <label className="vms-field">Camera password<PasswordField value={password} maxLength={1024} onChange={(event) => setPassword(event.target.value)} autoComplete="off" disabled={onboard.isPending} required /></label>
            {needsNewPassword && (
              <>
                <div className="rounded-lg border border-warning/40 bg-warning-subtle/40 px-4 py-2 text-xs text-foreground">
                  Set a new password on this camera (8–32 characters) before adding it. Use this new password in the VizenLink mobile app too.
                </div>
                <label className="vms-field">
                  New camera password
                  <PasswordField
                    value={newPassword}
                    maxLength={32}
                    onChange={(event) => {
                      setNewPassword(event.target.value);
                      setPasswordRuleError(null);
                    }}
                    autoComplete="new-password"
                    disabled={onboard.isPending}
                    required
                  />
                </label>
                <label className="vms-field">
                  Confirm new password
                  <PasswordField
                    value={confirmNewPassword}
                    maxLength={32}
                    onChange={(event) => {
                      setConfirmNewPassword(event.target.value);
                      setPasswordRuleError(null);
                    }}
                    autoComplete="new-password"
                    disabled={onboard.isPending}
                    required
                  />
                </label>
              </>
            )}
            {(passwordRuleError || (onboard.error && !(needsNewPassword && onboard.error.message === NEEDS_NEW_PASSWORD_MSG))) && (
              <p role="alert" className="text-sm text-critical">
                {passwordRuleError ?? onboard.error?.message}
              </p>
            )}
            <Button
              type="submit"
              disabled={
                !username.trim() ||
                !password ||
                (needsNewPassword && (!newPassword || !confirmNewPassword)) ||
                onboard.isPending
              }
            >
              {onboard.isPending
                ? needsNewPassword
                  ? "Updating camera password…"
                  : "Connecting to camera…"
                : needsNewPassword
                  ? "Set password & add camera"
                  : "Add camera"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
