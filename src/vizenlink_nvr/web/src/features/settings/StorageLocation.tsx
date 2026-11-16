import { Checkbox } from "@/components/ui/checkbox";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import type { StorageStatusResponse } from "@/features/dashboard/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SettingsSection } from "./SettingsSection";

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
  const dirty = path.trim() !== storage.storage_path || allowSystemDisk !== storage.allow_system_disk;
  return <form onSubmit={e => { e.preventDefault(); mutation.mutate(); }}>
    <SettingsSection
      title="Recording folder"
      description="Where footage is saved on the recorder. Changing the folder does not move existing recordings."
      footer={<Button type="submit" disabled={!path.trim() || !dirty || mutation.isPending}>{mutation.isPending ? "Saving…" : "Save recording folder"}</Button>}
    >
      <div className="flex flex-col gap-2">
        <label className="vms-field">Folder on the recorder<Input required className="font-mono" value={path} onChange={e => setPath(e.target.value)} placeholder="/path/to/recordings" disabled={mutation.isPending} /></label>
        <p className="text-xs text-muted-foreground">Use an absolute path to a writable folder on the NVR.</p>
      </div>
      <div className="flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={allowSystemDisk} onCheckedChange={checked => setAllowSystemDisk(checked === true)} disabled={mutation.isPending} />Allow recording on the system disk</label>
        <p className="text-xs text-muted-foreground">A separate recording drive is preferable. Using the system disk reduces space available to other applications.</p>
      </div>
      {mutation.isError && <p role="alert" className="text-sm text-critical">{mutation.error.message}</p>}
    </SettingsSection>
  </form>;
}
