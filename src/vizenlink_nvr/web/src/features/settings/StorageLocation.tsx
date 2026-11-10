import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import type { StorageStatusResponse } from "@/features/dashboard/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function StorageLocation({ storage }: { storage: StorageStatusResponse }) {
  const user = useCurrentUser();
  const client = useQueryClient();
  const [path, setPath] = useState(storage.storage_path);
  const [allowSystemDisk, setAllowSystemDisk] = useState(storage.allow_system_disk);
  const mutation = useMutation({
    mutationFn: () => apiFetch<StorageStatusResponse>("/api/v1/storage/set-path", {
      method: "POST",
      body: { storage_path: path.trim(), allow_system_disk: allowSystemDisk, reserve_bytes: storage.reserve_bytes },
    }),
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: ["storage", "status"] });
      await client.invalidateQueries({ queryKey: ["health"] });
      if (["ok", "healthy"].includes(result.health_state)) toast.success("Recording folder updated");
      else toast.error("Folder saved, but storage still needs attention. Check the storage message above.");
    },
  });
  if (user?.role !== "owner") return <p className="text-sm text-muted-foreground">Ask the recorder owner to change the recording folder.</p>;
  return <details className="rounded-xl border border-border bg-card p-6" open={!["ok", "healthy"].includes(storage.health_state) ? true : undefined}>
    <summary className="cursor-pointer font-semibold">Recording folder</summary>
    <form onSubmit={e => { e.preventDefault(); mutation.mutate(); }} className="mt-4 flex flex-col gap-4">
      <label className="vms-field">Folder on the recorder<Input required value={path} onChange={e => setPath(e.target.value)} placeholder="/path/to/recordings" disabled={mutation.isPending} /></label>
      <p className="text-sm text-muted-foreground">Use an absolute path to a writable folder on the NVR. Changing this location does not move existing recordings.</p>
      <label className="flex items-center gap-4 text-sm"><input type="checkbox" checked={allowSystemDisk} onChange={e => setAllowSystemDisk(e.target.checked)} disabled={mutation.isPending} />Allow recording on the system disk</label>
      <p className="text-xs text-muted-foreground">A separate recording drive is preferable. Using the system disk reduces space available to other applications.</p>
      {mutation.isError && <p role="alert" className="text-sm text-critical">{mutation.error.message}</p>}
      <Button type="submit" disabled={!path.trim() || mutation.isPending} className="self-start">{mutation.isPending ? "Saving…" : "Save recording folder"}</Button>
    </form>
  </details>;
}
