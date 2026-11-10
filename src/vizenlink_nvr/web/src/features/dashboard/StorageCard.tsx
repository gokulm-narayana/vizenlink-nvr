import React, { useState } from "react";
import { Link } from "react-router";
import { Copy, HardDrive, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/queries";
import type { StorageStatusResponse } from "./api";
import { DASHBOARD_COPY } from "./copy";

export interface StorageCardProps { storage: StorageStatusResponse | null }
export function middleEllipsis(str: string, maxLen = 32): string {
  if (!str || str.length <= maxLen) return str;
  const half = Math.floor((maxLen - 3) / 2);
  return `${str.slice(0, half)}...${str.slice(-half)}`;
}
export function bytesToGiB(bytes?: number | null): string {
  return `${(Math.max(0, bytes || 0) / (1024 ** 3)).toFixed(1)} GiB`;
}
export function storageSummary(storage: StorageStatusResponse): string {
  if (storage.health_reason?.toLowerCase().includes("permission denied")) return "The recorder cannot write to this folder. Choose a recording folder it can access.";
  const messages: Record<string, string> = {
    unmounted: "The recording drive or folder is unavailable. Reconnect the drive or choose another folder.",
    read_only: "The recording drive is read-only. Choose a writable drive to resume recording.",
    full: "The recording drive is full. Free up space or choose another drive.",
    system_disk_refused: "This folder is on the system disk. Choose a recording drive or explicitly allow this disk in storage settings.",
  };
  return messages[storage.health_state] || "Recording storage needs attention. Check the drive and recording folder.";
}
export const StorageCard: React.FC<StorageCardProps> = ({ storage }) => {
  const user = useCurrentUser();
  const [showFallback, setShowFallback] = useState(false);
  const healthy = !!storage && ["ok", "healthy"].includes(storage.health_state);
  const manage = user?.role === "owner" || user?.role === "operator";
  const handleCopy = async () => {
    if (!storage) return;
    try { await navigator.clipboard.writeText(storage.storage_path); toast(DASHBOARD_COPY.STORAGE_PATH_COPIED_TOAST); }
    catch { setShowFallback(true); }
  };
  return <Card className="min-w-0 gap-0 border-border bg-card py-0">
    <CardHeader className="flex flex-row items-center justify-between border-b border-border p-4">
      <div className="flex items-center gap-2"><HardDrive className="size-4 text-muted-foreground" /><CardTitle>{DASHBOARD_COPY.STORAGE_TITLE}</CardTitle></div>
      <span className={`text-xs ${healthy ? "text-success" : "text-warning"}`}>{storage ? healthy ? "Ready to record" : "Action needed" : "Unavailable"}</span>
    </CardHeader>
    <CardContent className="flex flex-col gap-4 p-4">
      {!healthy && storage && <div className="border-l-2 border-warning pl-3"><p className="font-semibold">Recording storage is not ready</p><p className="mt-1 text-sm text-muted-foreground">{storageSummary(storage)}</p>{manage && <Button asChild variant="outline" size="sm" className="mt-3"><Link to="/settings/recording">Review storage settings<ArrowUpRight className="size-4" /></Link></Button>}</div>}
      {healthy && storage && <div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-muted-foreground">{DASHBOARD_COPY.STORAGE_FREE}</p><p className="mt-1 text-xl font-semibold">{storage.telemetry ? bytesToGiB(storage.telemetry.free_bytes) : "Unavailable"}</p></div><div><p className="text-xs text-muted-foreground">{DASHBOARD_COPY.STORAGE_ESTIMATED_RETENTION}</p><p className="mt-1 text-xl font-semibold">{storage.estimated_retention_days != null ? `${storage.estimated_retention_days} days` : "Not estimated"}</p></div></div>}
      {storage && <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">Storage details</summary><div className="mt-3 flex flex-col gap-3"><div className="flex min-w-0 items-center gap-2"><span className="min-w-0 flex-1 break-all font-mono text-xs">{storage.storage_path}</span><Button variant="ghost" size="icon" aria-label={DASHBOARD_COPY.STORAGE_PATH_COPY_LABEL} onClick={handleCopy}><Copy className="size-4" /></Button></div>{showFallback && <><input readOnly aria-label="Storage path to copy" value={storage.storage_path} onFocus={e => e.target.select()} className="w-full rounded border border-input bg-background p-2" /><span>{DASHBOARD_COPY.STORAGE_PATH_FALLBACK_CAPTION}</span></>}<p className="text-xs text-muted-foreground">Reserved space: {bytesToGiB(storage.reserve_bytes)}</p>{!healthy && storage.health_reason && <p className="break-words text-xs text-muted-foreground">{storage.health_reason}</p>}</div></details>}
    </CardContent>
  </Card>;
};
