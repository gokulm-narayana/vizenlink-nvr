import { resolveTimezones } from "@/lib/timezones";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Clock, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineError } from "@/components/InlineError";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { formatDateTime } from "@/lib/time";
import { SettingsSection } from "./SettingsSection";

export type SystemInfo = { recorder_name: string; site_timezone: string; version: string };

/** Current time in a zone, or null while the typed zone is not a real one. */
function previewTime(zone: string): string | null {
  try {
    return formatDateTime(new Date(), zone, { second: undefined });
  } catch {
    return null;
  }
}

function SystemForm({ info }: { info: SystemInfo }) {
  const owner = useCurrentUser()?.role === "owner";
  const client = useQueryClient();
  const [zones] = useState(() => Array.from(new Set(["UTC", ...resolveTimezones().list])));
  const [name, setName] = useState(info.recorder_name);
  const [zone, setZone] = useState(info.site_timezone);
  const save = useMutation({
    mutationFn: () => apiFetch<SystemInfo>("/api/v1/system", {
      method: "PUT", body: { recorder_name: name.trim(), site_timezone: zone.trim() },
    }),
    onSuccess: async result => {
      client.setQueryData(["system"], result);
      await client.invalidateQueries();
      toast.success("System settings saved");
    },
  });
  const dirty = name !== info.recorder_name || zone !== info.site_timezone;
  const now = zone.trim() ? previewTime(zone.trim()) : null;
  return <>
    <form onSubmit={e => { e.preventDefault(); save.mutate(); }}>
      <SettingsSection
        title="Recorder"
        description={owner ? "The name people see for this recorder and the time zone used for every time on screen." : "Only the owner can change these settings."}
        footer={owner && <>
          <Button type="button" variant="outline" disabled={!dirty || save.isPending} onClick={() => { setName(info.recorder_name); setZone(info.site_timezone); }}>Discard changes</Button>
          <Button type="submit" disabled={save.isPending || !name.trim() || !zone.trim() || !dirty}><Save className="size-4" />{save.isPending ? "Saving…" : "Save system settings"}</Button>
        </>}
      >
        <fieldset disabled={!owner || save.isPending} className="grid gap-6 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <label className="vms-field">Recorder name<Input required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label>
            <p className="text-xs text-muted-foreground">Shown in the mobile app when it finds this recorder.</p>
          </div>
          <div className="flex flex-col gap-2">
            <label className="vms-field">Site time zone<Input required list="site-zones" value={zone} onChange={e => setZone(e.target.value)} /></label>
            <datalist id="site-zones">{zones.map(value => <option key={value} value={value} />)}</datalist>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-4 shrink-0" aria-hidden />
              {now ? `Time there now: ${now}` : "Type a region and city, for example Asia/Kolkata."}
            </p>
          </div>
        </fieldset>
        {save.error && <p role="alert" className="text-sm text-critical">{save.error.message}</p>}
      </SettingsSection>
    </form>
    <SettingsSection title="About">
      <dl className="grid gap-4 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-muted-foreground">Product</dt><dd className="mt-1 font-semibold">VizenLink NVR</dd></div>
        <div><dt className="text-xs text-muted-foreground">Version</dt><dd className="mt-1 font-semibold tabular-nums">{info.version}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Recorder name</dt><dd className="mt-1 truncate font-semibold">{info.recorder_name}</dd></div>
      </dl>
    </SettingsSection>
  </>;
}

export function SystemSettings() {
  const info = useQuery({ queryKey: ["system"], queryFn: () => apiFetch<SystemInfo>("/api/v1/system") });
  if (info.isError) return <InlineError message={info.error.message} actionLabel="Retry system settings" onAction={() => void info.refetch()} />;
  if (!info.data) return <p role="status" className="text-sm text-muted-foreground">Loading system settings…</p>;
  return <SystemForm key={JSON.stringify(info.data)} info={info.data} />;
}
