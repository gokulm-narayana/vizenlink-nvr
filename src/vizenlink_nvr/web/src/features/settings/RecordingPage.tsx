import { NativeSelect } from "@/components/ui/native-select";
import { Checkbox } from "@/components/ui/checkbox";
import { useEffect, useState } from "react";
import { Link, useBlocker } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useCameras, useRecordingStatus, type RecordingStatusItem } from "@/lib/queries";
import { useSiteTimeZone } from "@/lib/time";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/InlineError";
import { SettingsSection } from "./SettingsSection";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
function parseSchedule(value: string): boolean[][] | null {
  try {
    const saved = JSON.parse(value);
    const grid = Array.isArray(saved) ? saved : saved.days ?? days.map(day => saved[day.toLowerCase()]);
    if (Array.isArray(grid) && grid.length === 7 && grid.every(row => Array.isArray(row) && row.length === 24)) {
      return grid.map(row => row.map(Boolean));
    }
  } catch { /* Preserve unknown schedules until a preset is selected. */ }
  return null;
}
const fields = [
  ["mode", "Recording mode"], ["schedule_json", "Weekly schedule"], ["audio_enabled", "Audio"],
  ["retention_days", "Retention days"], ["retention_max_gb", "Storage limit"],
] as const;
type PolicyField = typeof fields[number][0];

function RecordingForm({ item, name, serials, onEditing }: {
  item: RecordingStatusItem; name: string; serials: string[]; onEditing: (editing: boolean) => void;
}) {
  const bulk = serials.length > 1;
  const [included, setIncluded] = useState<PolicyField[]>([]);
  const enabled = (field: PolicyField) => !bulk || included.includes(field);
  const client = useQueryClient();
  const zone = useSiteTimeZone();
  const [mode, setMode] = useState(item.mode);
  const [audio, setAudio] = useState(Boolean(item.audio_enabled));
  const [retention, setRetention] = useState(String(item.retention_days ?? ""));
  const [limit, setLimit] = useState(String(item.retention_max_gb ?? ""));
  const [schedule, setSchedule] = useState(() => parseSchedule(item.schedule_json));
  const [scheduleChanged, setScheduleChanged] = useState(false);
  const dirty = bulk ? included.length > 0 : mode !== item.mode || audio !== Boolean(item.audio_enabled) || retention !== String(item.retention_days ?? "") || limit !== String(item.retention_max_gb ?? "") || scheduleChanged;
  const mutation = useMutation({
    mutationFn: () => {
      const values: Record<PolicyField, unknown> = {
        mode, audio_enabled: audio, retention_days: retention ? Number(retention) : null,
        retention_max_gb: limit ? Number(limit) : null, schedule_json: JSON.stringify({ days: schedule }),
      };
      const changes = Object.fromEntries(fields.filter(([field]) =>
        enabled(field) && (field !== "schedule_json" || (schedule && (bulk || scheduleChanged)))
      ).map(([field]) => [field, values[field]]));
      if (bulk) return apiFetch("/api/v1/recording/apply", { method: "POST", body: { serials, changes } });
      return apiFetch(`/api/v1/recording/${encodeURIComponent(item.camera_serial)}`, { method: "PATCH", body: changes });
    },
    onSuccess: async () => {
      setIncluded([]); setScheduleChanged(false);
      await client.invalidateQueries({ queryKey: ["recordingStatus"] });
      toast.success(bulk ? `Recording settings saved for ${serials.length} cameras` : `Recording settings saved for ${name}`);
    },
    onError: () => { void client.invalidateQueries({ queryKey: ["recordingStatus"] }); },
  });
  const blocker = useBlocker(dirty && !mutation.isPending);
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
    <div><h2 className="text-xl font-semibold">{bulk ? `Edit ${serials.length} cameras` : name}</h2><p className="mt-1 text-sm text-muted-foreground">{bulk ? `Choose which settings to apply. Starting values are from ${name}.` : "Live video can stay on when recording is off."}</p></div>
    <fieldset disabled={mutation.isPending} className="flex flex-col gap-6">
      {bulk && <fieldset className="flex flex-wrap gap-4"><legend className="mb-2 font-semibold">Settings to apply</legend>
        {fields.map(([field, label]) => <label key={field} className="flex items-center gap-2 text-sm">
          <Checkbox checked={included.includes(field)} onCheckedChange={checked => setIncluded(prev => checked === true ? [...prev, field] : prev.filter(f => f !== field))} />{label}
        </label>)}
      </fieldset>}
      <label className="vms-field">When to record<NativeSelect className="max-w-md" disabled={!enabled("mode")} value={mode} onChange={e => setMode(e.target.value)}><option value="continuous">All the time</option><option value="scheduled">On a weekly schedule</option><option value="event">Event mode (rolling buffer)</option><option value="off">Recording off</option></NativeSelect></label>
      {mode === "off" && <p className="rounded-lg bg-warning-subtle p-4 text-sm text-warning">New footage will not be recorded after you save. Existing footage remains subject to retention rules.</p>}
      {mode === "event" && <p className="text-sm text-muted-foreground">The recorder keeps a rolling buffer and protects footage associated with events.</p>}
      {((!bulk && mode === "scheduled") || (bulk && enabled("schedule_json"))) && <section className="flex flex-col gap-4"><h3 className="font-semibold">Weekly schedule</h3><p className="text-sm text-muted-foreground">Selected hours will be recorded in {zone}. Each box covers one hour.</p><div className="flex flex-wrap gap-2">{[["always", "Every day"], ["weekdays", "Weekdays"], ["office", "Mon–Fri, 09:00–18:00"], ["none", "Clear"]].map(([v, label]) => <Button key={v} type="button" variant="outline" size="sm" onClick={() => applyPreset(v)}>{label}</Button>)}</div>{schedule ? <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th className="pr-4 text-left">Day</th>{Array.from({ length: 24 }, (_, h) => <th key={h} className="min-w-8 py-2">{String(h).padStart(2, "0")}</th>)}</tr></thead><tbody>{days.map((day, d) => <tr key={day}><th className="pr-4 text-left font-normal">{day.slice(0, 3)}</th>{schedule[d].map((enabled, h) => <td key={h} className="p-0.5"><button type="button" aria-label={`${day} ${String(h).padStart(2, "0")}:00`} aria-pressed={enabled} className={`h-8 w-8 rounded border ${enabled ? "border-primary bg-primary text-primary-foreground" : "border-border bg-muted"}`} onClick={() => { setSchedule(schedule.map((row, ri) => row.map((v, hi) => ri === d && hi === h ? !v : v))); setScheduleChanged(true); }}>{enabled ? "✓" : "·"}</button></td>)}</tr>)}</tbody></table></div> : <p className="text-sm text-muted-foreground">Your existing schedule will be kept. Select a preset to replace it.</p>}</section>}
      <label className="flex items-center gap-4"><Checkbox disabled={!enabled("audio_enabled")} checked={audio} onCheckedChange={checked => setAudio(checked === true)} />Include audio when supported by the camera</label>
      <div className="grid gap-4 sm:grid-cols-2"><label className="vms-field">Keep footage for (days)<Input type="number" min="1" step="1" disabled={!enabled("retention_days")} placeholder="No day limit" value={retention} onChange={e => setRetention(e.target.value)} /></label><label className="vms-field">Camera storage limit (GB)<Input type="number" min="1" step="1" disabled={!enabled("retention_max_gb")} placeholder="No camera limit" value={limit} onChange={e => setLimit(e.target.value)} /></label></div>
      <p className="text-sm text-muted-foreground">Leave limits blank to remove them. Available disk space can shorten retention. Reducing limits can remove older, unprotected footage.</p>
    </fieldset>
    {mutation.isError && <p role="alert" className="text-critical">{mutation.error.message}. Review the current settings before retrying.</p>}
    <div className="flex flex-wrap justify-end gap-4 border-t border-border pt-4"><Button type="button" variant="outline" disabled={!dirty || mutation.isPending} onClick={() => { setIncluded([]); setMode(item.mode); setAudio(Boolean(item.audio_enabled)); setRetention(String(item.retention_days ?? "")); setLimit(String(item.retention_max_gb ?? "")); setSchedule(parseSchedule(item.schedule_json)); setScheduleChanged(false); }}>Discard changes</Button><Button type="submit" disabled={!dirty || mutation.isPending || (bulk && included.includes("schedule_json") && !schedule)}><Save className="size-4" />{mutation.isPending ? "Saving…" : bulk ? `Apply to selected (${serials.length})` : "Save recording settings"}</Button></div>
  </form>;
}
// Same wording as the "When to record" dropdown below, so the table and the form agree.
const MODE_BADGE: Record<string, { text: string; cls: string }> = {
  continuous: { text: "All the time", cls: "bg-success-subtle text-success" },
  scheduled: { text: "Scheduled", cls: "bg-selected text-selected-foreground" },
  event: { text: "Event mode", cls: "bg-warning-subtle text-warning" },
  off: { text: "Off", cls: "bg-muted text-muted-foreground" },
};
interface RecordingOptions { clip_minutes: number; clip_minutes_choices: number[] }
const clipLabel = (minutes: number) => minutes === 60 ? "1 hour" : minutes === 1 ? "1 minute" : `${minutes} minutes`;

/** Recorder-wide: how long each saved clip (one file) is. */
function ClipLength() {
  const client = useQueryClient();
  const options = useQuery({ queryKey: ["recording", "options"], queryFn: () => apiFetch<RecordingOptions>("/api/v1/recording/options"), retry: false });
  const [choice, setChoice] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: (clip_minutes: number) => apiFetch<RecordingOptions>("/api/v1/recording/options", { method: "PUT", body: { clip_minutes } }),
    onSuccess: async (saved) => {
      client.setQueryData(["recording", "options"], saved);
      setChoice(null);
      toast.success(`New clips will be ${clipLabel(saved.clip_minutes)} long`);
    },
  });
  if (!options.data?.clip_minutes_choices?.length) return null;
  const current = options.data.clip_minutes;
  const value = choice ?? current;
  return <SettingsSection title="Clip length"
    description="Footage is saved as a series of clips. This sets how long each clip is, for every camera."
    footer={<Button disabled={value === current || mutation.isPending} onClick={() => mutation.mutate(value)}><Save className="size-4" />{mutation.isPending ? "Saving…" : "Save clip length"}</Button>}>
    <label className="vms-field">Length of each clip
      <NativeSelect className="max-w-md" value={value} disabled={mutation.isPending} onChange={e => setChoice(Number(e.target.value))}>
        {options.data.clip_minutes_choices.map(m => <option key={m} value={m}>{clipLabel(m)}</option>)}
      </NativeSelect>
    </label>
    <p className="text-sm text-muted-foreground">Applies to new footage within about 30 seconds; clips already saved keep their length. Recording restarts briefly on each camera when this changes.</p>
    {value > 1 && <p className="rounded-lg bg-warning-subtle p-4 text-sm text-warning">A clip shows up in Playback when it is finished, so with {clipLabel(value)} clips the newest footage can take up to {clipLabel(value)} to appear, and a camera that stops recording is reported after about {clipLabel(value * 2)}.</p>}
    {mutation.isError && <p role="alert" className="text-sm text-critical">{mutation.error.message}</p>}
  </SettingsSection>;
}

export function RecordingPage() {
  const cameras = useCameras();
  const recording = useRecordingStatus();
  const [selection, setSelection] = useState<string[] | null>(null);
  const [editing, setEditing] = useState(false);
  const rows = cameras.data ?? [];
  const serials = selection?.filter(s => rows.some(c => c.serial === s)) ?? rows.slice(0, 1).map(c => c.serial);
  const selected = rows.find(c => serials.includes(c.serial));
  const item = recording.data?.find(r => r.camera_serial === selected?.serial);
  function choose(next: string[]) {
    if (!editing || window.confirm("Discard unsaved recording changes and change selection?")) setSelection(next);
  }
  if (cameras.isLoading || recording.isLoading) return <p role="status">Loading recording settings…</p>;
  if (cameras.isError || recording.isError) return <InlineError message="Couldn't load recording settings." actionLabel="Retry settings" onAction={() => { void cameras.refetch(); void recording.refetch(); }} />;
  if (!rows.length) return <div><p>Add a camera to configure recording.</p><Button asChild><Link to="/cameras/add">Add camera</Link></Button></div>;
  return <div className="flex min-w-0 flex-col gap-4 lg:gap-6">
    <ClipLength />
    <SettingsSection flush title="Camera recording policies"
      description="Tick one camera to edit it, or several to apply the same change to all of them."
      action={<span className="text-sm text-muted-foreground" role="status">{serials.length} of {rows.length} selected</span>}>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="w-12 px-6 py-2"><Checkbox aria-label="Select all cameras" checked={serials.length === rows.length ? true : serials.length ? "indeterminate" : false} onCheckedChange={checked => choose(checked ? rows.map(c => c.serial) : [])} /></th>
        {["Camera", "Mode", "Audio", "Retention"].map(label => <th key={label} scope="col" className="px-4 py-2 font-semibold">{label}</th>)}</tr></thead>
        <tbody>{rows.map(camera => {
          const policy = recording.data?.find(r => r.camera_serial === camera.serial);
          const picked = serials.includes(camera.serial);
          return <tr key={camera.serial} data-selected={picked} className={`border-t border-border ${picked ? "bg-selected/40" : "hover:bg-muted/40"}`}>
            <td className="px-6 py-2"><Checkbox aria-label={`Select ${camera.name}`} checked={picked}
              onCheckedChange={checked => choose(checked ? [...serials, camera.serial] : serials.filter(s => s !== camera.serial))} /></td>
            <th scope="row" className="px-4 py-2 font-semibold">{camera.name}</th>
            <td className="px-4 py-2"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${MODE_BADGE[policy?.mode ?? ""]?.cls ?? "bg-muted text-muted-foreground"}`}>{MODE_BADGE[policy?.mode ?? ""]?.text ?? "Unavailable"}</span></td>
            <td className="px-4 py-2 text-muted-foreground">{policy ? policy.audio_enabled ? "On" : "Off" : "—"}</td>
            <td className="px-4 py-2 tabular-nums text-muted-foreground">{policy?.retention_days ? `${policy.retention_days} days` : "No day limit"}</td>
          </tr>;
        })}</tbody>
      </table></div>
    </SettingsSection>
    {item && selected ? <RecordingForm key={JSON.stringify([serials, ...fields.map(([field]) => item[field])])}
      item={item} name={selected.name} serials={serials} onEditing={setEditing} /> : <p>Select a camera with a recording policy to edit.</p>}
  </div>;
}
