import { useEffect, useState } from "react";
import { Link, useBlocker } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Save } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useCameras, useRecordingStatus, type RecordingStatusItem } from "@/lib/queries";
import { useSiteTimeZone } from "@/lib/time";
import { useStorageStatus } from "@/features/dashboard/api";
import { StorageLocation } from "./StorageLocation";
import { StorageCard } from "@/features/dashboard/StorageCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/InlineError";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
function parseSchedule(value: string): boolean[][] | null {
  try { const p = JSON.parse(value); const grid = p.days ?? p;
    if (Array.isArray(grid) && grid.length === 7 && grid.every(d => Array.isArray(d) && d.length === 24)) return grid.map(d => d.map(Boolean));
  } catch { /* Preserve unknown schedules unless the user explicitly chooses a preset. */ }
  return null;
}
function RecordingForm({ item, name, onEditing }: { item: RecordingStatusItem; name: string; onEditing: (editing: boolean) => void }) {
  const client = useQueryClient();
  const zone = useSiteTimeZone();
  const [mode, setMode] = useState(item.mode);
  const [audio, setAudio] = useState(Boolean(item.audio_enabled));
  const [retention, setRetention] = useState(String(item.retention_days ?? ""));
  const [limit, setLimit] = useState(String(item.retention_max_gb ?? ""));
  const [schedule, setSchedule] = useState(() => parseSchedule(item.schedule_json));
  const [scheduleChanged, setScheduleChanged] = useState(false);
  const dirty = mode !== item.mode || audio !== Boolean(item.audio_enabled) || retention !== String(item.retention_days ?? "") || limit !== String(item.retention_max_gb ?? "") || scheduleChanged;
  const mutation = useMutation({
    mutationFn: () => apiFetch(`/api/v1/recording/${encodeURIComponent(item.camera_serial)}`, { method: "PATCH", body: {
      mode, audio_enabled: audio,
      retention_days: retention ? Number(retention) : null,
      retention_max_gb: limit ? Number(limit) : null,
      ...(scheduleChanged && schedule ? { schedule_json: JSON.stringify({ days: schedule }) } : {}),
    } }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["recordingStatus"] }); toast.success(`Recording settings saved for ${name}`); },
    onError: () => { void client.invalidateQueries({ queryKey: ["recordingStatus"] }); },
  });
  const blocker = useBlocker(dirty && !mutation.isSuccess);
  useEffect(() => { onEditing(dirty || mutation.isPending); return () => onEditing(false); }, [dirty, mutation.isPending, onEditing]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const applyPreset = (preset: string) => {
    setSchedule(days.map((_, d) => Array.from({ length: 24 }, (_, h) => preset === "always" || (preset === "weekdays" && d < 5) || (preset === "office" && d < 5 && h >= 9 && h < 18))));
    setScheduleChanged(true);
  };
  return <form onSubmit={e => { e.preventDefault(); mutation.mutate(); }} className="flex min-w-0 flex-col gap-6 rounded-xl border border-border bg-card p-6">
    {blocker.state === "blocked" && <div role="alert" className="rounded-lg border border-warning p-4"><p>You have unsaved recording changes.</p><div className="mt-4 flex gap-2"><Button type="button" variant="outline" onClick={() => blocker.reset()}>Keep editing</Button><Button type="button" onClick={() => blocker.proceed()}>Discard and leave</Button></div></div>}
    <div><h2 className="text-xl font-semibold">{name}</h2><p className="mt-1 text-sm text-muted-foreground">These are recording preferences. Live video can stay on when recording is off.</p></div>
    <fieldset disabled={mutation.isPending} className="flex flex-col gap-6">
      <label className="vms-field">When to record<select className="vms-select" value={mode} onChange={e => setMode(e.target.value)}><option value="continuous">All the time</option><option value="scheduled">On a weekly schedule</option><option value="event">Event mode (rolling buffer)</option><option value="off">Recording off</option></select></label>
      {mode === "off" && <p className="rounded-lg bg-warning-subtle p-4 text-sm text-warning">New footage will not be recorded after you save. Existing footage remains subject to retention rules.</p>}
      {mode === "event" && <p className="text-sm text-muted-foreground">The recorder keeps a rolling buffer and protects footage associated with events.</p>}
      {mode === "scheduled" && <section className="flex flex-col gap-4"><h3 className="font-semibold">Weekly schedule</h3><p className="text-sm text-muted-foreground">Selected hours will be recorded in {zone}. Each box covers one hour.</p><div className="flex flex-wrap gap-2">{[["always", "Every day"], ["weekdays", "Weekdays"], ["office", "Mon–Fri, 09:00–18:00"], ["none", "Clear"]].map(([v, label]) => <Button key={v} type="button" variant="outline" size="sm" onClick={() => applyPreset(v)}>{label}</Button>)}</div>{schedule ? <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th className="pr-4 text-left">Day</th>{Array.from({ length: 24 }, (_, h) => <th key={h} className="min-w-8 py-2">{String(h).padStart(2, "0")}</th>)}</tr></thead><tbody>{days.map((day, d) => <tr key={day}><th className="pr-4 text-left font-normal">{day.slice(0, 3)}</th>{schedule[d].map((enabled, h) => <td key={h} className="p-0.5"><button type="button" aria-label={`${day} ${String(h).padStart(2, "0")}:00`} aria-pressed={enabled} className={`h-8 w-8 rounded border ${enabled ? "border-primary bg-primary text-primary-foreground" : "border-border bg-muted"}`} onClick={() => { setSchedule(schedule.map((row, ri) => row.map((v, hi) => ri === d && hi === h ? !v : v))); setScheduleChanged(true); }}>{enabled ? "✓" : "·"}</button></td>)}</tr>)}</tbody></table></div> : <p className="text-sm text-muted-foreground">Your existing schedule will be kept. Select a preset to replace it.</p>}</section>}
      <label className="flex items-center gap-4"><input type="checkbox" checked={audio} onChange={e => setAudio(e.target.checked)} />Include audio when supported by the camera</label>
      <div className="grid gap-4 sm:grid-cols-2"><label className="vms-field">Keep footage for (days)<Input type="number" min="1" step="1" placeholder="No day limit" value={retention} onChange={e => setRetention(e.target.value)} /></label><label className="vms-field">Camera storage limit (GB)<Input type="number" min="1" step="1" placeholder="No camera limit" value={limit} onChange={e => setLimit(e.target.value)} /></label></div>
      <p className="text-sm text-muted-foreground">Leave limits blank to remove them. Available disk space can shorten retention. Reducing limits can remove older, unprotected footage.</p>
    </fieldset>
    {mutation.isError && <p role="alert" className="text-critical">{mutation.error.message}. Review the current settings before retrying.</p>}
    <div className="flex flex-wrap justify-end gap-4 border-t border-border pt-4"><Button type="button" variant="outline" disabled={!dirty || mutation.isPending} onClick={() => { setMode(item.mode); setAudio(Boolean(item.audio_enabled)); setRetention(String(item.retention_days ?? "")); setLimit(String(item.retention_max_gb ?? "")); setSchedule(parseSchedule(item.schedule_json)); setScheduleChanged(false); }}>Discard changes</Button><Button type="submit" disabled={!dirty || mutation.isPending}><Save className="size-4" />{mutation.isPending ? "Saving…" : "Save recording settings"}</Button></div>
  </form>;
}
export function RecordingPage() {
  const cameras = useCameras(); const recording = useRecordingStatus(); const storage = useStorageStatus();
  const [serial, setSerial] = useState("");
  const [editing, setEditing] = useState(false);
  const selected = cameras.data?.find(c => c.serial === serial) || cameras.data?.[0];
  const item = recording.data?.find(r => r.camera_serial === selected?.serial);
  return <div className="flex min-w-0 flex-col gap-6"><Link to="/settings" className="inline-flex items-center gap-2 text-sm text-primary"><ArrowLeft className="size-4" />All settings</Link>
    {storage.isError ? <InlineError message="Couldn't load storage." actionLabel="Retry storage" onAction={() => void storage.refetch()} /> : storage.data ? <StorageCard storage={storage.data} /> : <p role="status">Loading storage…</p>}
    {storage.data && <StorageLocation key={storage.data.storage_path} storage={storage.data} />}
    {cameras.isLoading || recording.isLoading ? <p role="status">Loading recording settings…</p> : cameras.isError || recording.isError ? <InlineError message="Couldn't load recording settings." actionLabel="Retry settings" onAction={() => { void cameras.refetch(); void recording.refetch(); }} /> : !selected ? <div className="rounded-xl border border-border bg-card p-8"><p>Add a camera to configure recording.</p><Button asChild className="mt-4"><Link to="/cameras/add">Add camera</Link></Button></div> : <><label className="vms-field">Camera<select className="vms-select" value={selected.serial} onChange={e => { if (!editing || window.confirm("Discard unsaved recording changes and switch camera?")) setSerial(e.target.value); }}>{cameras.data?.map(c => <option key={c.serial} value={c.serial}>{c.name}</option>)}</select></label>{item ? <RecordingForm key={`${item.camera_serial}:${JSON.stringify(item)}`} item={item} name={selected.name} onEditing={setEditing} /> : <p>No recording policy is available for this camera.</p>}</>}
  </div>;
}
