import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/InlineError";
import { StorageCard } from "@/features/dashboard/StorageCard";
import { useStorageStatus } from "@/features/dashboard/api";
import { apiFetch } from "@/lib/api";
import { RefreshCw } from "lucide-react";
import { StorageLocation } from "./StorageLocation";
import { SettingsSection } from "./SettingsSection";

export function StoragePage() {
  const storage = useStorageStatus();
  const client = useQueryClient();
  const scan = useMutation({
    mutationFn: () => apiFetch<{ adopted: number; missing_marked: number; truncated_marked: number; total_valid: number }>("/api/v1/storage/scan", { method: "POST" }),
    onSuccess: () => client.invalidateQueries(),
  });
  if (storage.isError) return <InlineError message="Couldn't load storage." actionLabel="Retry storage" onAction={() => void storage.refetch()} />;
  if (!storage.data) return <p role="status">Loading storage…</p>;
  return <div className="flex flex-col gap-4 lg:gap-6">
    <StorageCard storage={storage.data} />
    <StorageLocation key={storage.data.storage_path} storage={storage.data} />
    <SettingsSection
      title="Recording index"
      description="The recorder keeps a list of every saved file. Rescan if footage on the disk is missing from Playback, for example after moving or restoring a drive. Recording continues during a rescan."
      action={<Button variant="outline" disabled={scan.isPending} onClick={() => scan.mutate()}><RefreshCw className={scan.isPending ? "size-4 animate-spin" : "size-4"} />{scan.isPending ? "Scanning…" : "Rescan storage"}</Button>}
    >
      {scan.data && <dl role="status" className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        {[["Valid segments", scan.data.total_valid], ["Added", scan.data.adopted], ["Marked missing", scan.data.missing_marked], ["Marked truncated", scan.data.truncated_marked]].map(([label, value]) =>
          <div key={label} className="rounded-lg bg-muted/40 p-4"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd></div>)}
      </dl>}
      {scan.error && <p role="alert" className="text-sm text-critical">{scan.error.message}</p>}
      {!scan.data && !scan.error && <p className="text-sm text-muted-foreground">No rescan run in this session.</p>}
    </SettingsSection>
  </div>;
}
