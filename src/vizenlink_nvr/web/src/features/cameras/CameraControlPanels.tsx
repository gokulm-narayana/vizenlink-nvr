import { Checkbox } from "@/components/ui/checkbox";
import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, Loader2, Megaphone, Mic, RefreshCw, Siren, Sun, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { InlineError } from "@/components/InlineError";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";

/* Hand-built screens for the most used camera_api groups. They read and write the same
   /features endpoints as the generic forms; the backend validates every payload against
   the pinned camera contract and the camera's reported capabilities. */

export interface FeatureStateData {
  title: string;
  description: string;
  capabilities: Record<string, any>;
  values: Record<string, Record<string, any>>;
  errors: Record<string, string>;
  operations: Array<{ id: string }>;
}

interface PanelProps {
  serial: string;
  cameraName: string;
  /** Generic forms for the operations this screen does not cover. */
  advanced: (handled: string[]) => ReactNode;
}

const EVENT_NAMES: Record<string, [string, string]> = {
  PersonDetected: ["Person detected", "A person is seen in the picture."],
  Loitering: ["Loitering", "A person stays in view longer than the loitering time."],
  Tamper: ["Camera tampering", "The camera is covered, moved or blinded."],
  VideoModeChanged: ["Day / night switch", "The camera changes between day and night mode."],
  PrivacyModeChanged: ["Privacy mode changed", "Privacy mode is switched on or off on the camera."],
  MotionDetected: ["Motion", "Movement anywhere in the picture."],
  VehicleDetected: ["Vehicle detected", "A vehicle is seen in the picture."],
  SoundDetected: ["Sound", "A loud sound is heard."],
};
const ACTION_NAMES: Record<string, string> = {
  mobile_alert: "Phone alert",
  siren: "Siren",
  spotlight: "Spotlight",
  warning: "Voice warning",
  buzzer: "Buzzer",
};
const humanize = (key: string) =>
  key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
const eventName = (event: string) => EVENT_NAMES[event]?.[0] ?? humanize(event);
const actionName = (action: string) => ACTION_NAMES[action] ?? humanize(action);

function useFeatureGroup(serial: string, group: string) {
  return useQuery({
    queryKey: ["cameraFeatures", serial, group],
    queryFn: ({ signal }) =>
      apiFetch<FeatureStateData>(`/api/v1/cameras/${encodeURIComponent(serial)}/features/${group}`, { signal }),
    retry: false,
    staleTime: 30000,
  });
}

function useCameraAction(serial: string, group: string) {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0,
    mutationFn: ({ op, payload, confirm }: { op: string; payload: Record<string, unknown>; confirm?: boolean }) =>
      apiFetch<{ output: Record<string, any> }>(
        `/api/v1/cameras/${encodeURIComponent(serial)}/features/actions/${op}`,
        { method: "POST", body: { payload, query: {}, confirmation: confirm ? serial : undefined } },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["cameraFeatures", serial, group] }),
  });
}

function useCanChange() {
  const user = useCurrentUser();
  return user?.role === "owner" || user?.role === "operator";
}

function Card({ icon, title, description, children }: { icon: ReactNode; title: string; description?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-6">
      <div className="mb-4 flex items-start gap-2">
        <span className="mt-1 text-primary-text">{icon}</span>
        <div>
          <h3 className="font-semibold">{title}</h3>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

function ReadError({ message }: { message?: string }) {
  if (!message) return null;
  return <p role="alert" className="mb-4 rounded-lg bg-warning-subtle p-4 text-sm text-warning">Could not read this from the camera: {message}</p>;
}

function SaveFeedback({ mutation }: { mutation: { isSuccess: boolean; error: Error | null } }) {
  if (mutation.error) return <p role="alert" className="mt-4 rounded-lg bg-critical-subtle p-4 text-sm text-critical">{mutation.error.message}</p>;
  if (mutation.isSuccess) return <p role="status" className="mt-4 flex items-center gap-2 text-sm text-success"><Check className="size-4" />Camera confirmed the change</p>;
  return null;
}

function ViewerNote({ canChange }: { canChange: boolean }) {
  return canChange ? null : <p className="mt-2 text-xs text-muted-foreground">Ask an operator or owner to change these settings.</p>;
}

function SwitchRow({ label, description, checked, disabled, onChange }: { label: string; description?: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0">
        <p className="text-sm font-semibold">{label}</p>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      <Switch aria-label={label} checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </div>
  );
}

/** Slider plus an exact number box: wide camera ranges (e.g. loitering up to many minutes)
    are hard to hit precisely with a slider alone. Typed values are clamped to the camera's range. */
function LevelField({ label, value, min, max, unit, disabled, onChange }: { label: string; value: number | undefined; min: number; max: number; unit?: string; disabled?: boolean; onChange: (v: number) => void }) {
  const current = value ?? min;
  const [typed, setTyped] = useState(String(current));
  useEffect(() => setTyped(String(current)), [current]);
  const commit = (text: string) => {
    const n = Math.round(Number(text));
    if (text.trim() === "" || !Number.isFinite(n)) { setTyped(String(current)); return; }
    const clamped = Math.min(max, Math.max(min, n));
    setTyped(String(clamped));
    if (clamped !== current) onChange(clamped);
  };
  return (
    <div className="vms-field">
      <span className="flex items-center justify-between gap-2">
        <span>{label}</span>
        <span className="flex items-center gap-1">
          <Input aria-label={`${label} value`} type="number" inputMode="numeric" min={min} max={max} step={1} value={typed} disabled={disabled}
            className="h-8 w-24 text-right" onChange={e => setTyped(e.target.value)} onBlur={e => commit(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); commit((e.target as HTMLInputElement).value); } }} />
          {unit && <span className="text-xs text-muted-foreground">{unit.trim()}</span>}
        </span>
      </span>
      <input aria-label={label} type="range" min={min} max={max} step={1} value={current} disabled={disabled}
        onChange={e => onChange(Number(e.target.value))} className="w-full accent-primary" />
      <span className="flex justify-between text-xs text-muted-foreground"><span>{min}{unit ?? ""}</span><span>{max}{unit ?? ""}</span></span>
    </div>
  );
}

/** Names what this camera lacks instead of silently hiding it. */
function NotSupported({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <p role="note" className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
      Not available on this camera: {items.join(", ")}.
    </p>
  );
}

/** Confirmation for actions that make the camera do something audible or visible. */
function ConfirmAction({ open, title, description, confirmLabel, onConfirm, onOpenChange }: { open: boolean; title: string; description: string; confirmLabel: string; onConfirm: () => void; onOpenChange: (open: boolean) => void }) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it off</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function PanelFrame({ serial, group, title, description, render }: { serial: string; group: string; title: string; description: string; render: (data: FeatureStateData) => ReactNode }) {
  const state = useFeatureGroup(serial, group);
  if (state.isPending) return <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-8 text-sm"><Loader2 className="size-4 animate-spin" />Reading settings from the camera…</div>;
  if (state.error) return <InlineError message={state.error.message} actionLabel="Reload camera settings" onAction={() => void state.refetch()} />;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        </div>
        <Button variant="outline" disabled={state.isFetching} onClick={() => void state.refetch()}><RefreshCw className="size-4" />Refresh camera values</Button>
      </div>
      {render(state.data!)}
    </div>
  );
}

/* ------------------------------------------------------------------ Detection */

function DetectionContent({ serial, data, advanced }: { serial: string; data: FeatureStateData; advanced: PanelProps["advanced"] }) {
  const canChange = useCanChange();
  const caps = data.capabilities;
  const prefsRead = data.values.getEventPreferences;
  const actionsRead = data.values.getEventResponseActions;
  const actionOptions: Record<string, string[]> = caps.supported_event_deterrence_options ?? {};
  const events: string[] = caps.supported_event_types ?? Object.keys(prefsRead ?? {});
  const [prefs, setPrefs] = useState<Record<string, boolean>>({});
  const [actions, setActions] = useState<Record<string, string[]>>({});
  useEffect(() => { setPrefs({ ...(prefsRead ?? {}) }); setActions({ ...(actionsRead ?? {}) }); }, [prefsRead, actionsRead]);
  const save = useCameraAction(serial, "detection");
  const prefsChanged = events.some(e => (prefs[e] ?? false) !== (prefsRead?.[e] ?? false));
  const actionsChanged = Object.keys(actionOptions).some(e => JSON.stringify([...(actions[e] ?? [])].sort()) !== JSON.stringify([...(actionsRead?.[e] ?? [])].sort()));
  const apply = async () => {
    if (prefsChanged) await save.mutateAsync({ op: "setEventPreferences", payload: Object.fromEntries(events.map(e => [e, prefs[e] ?? false])) });
    if (actionsChanged) await save.mutateAsync({ op: "setEventResponseActions", payload: Object.fromEntries(Object.keys(actionOptions).map(e => [e, actions[e] ?? []])) });
  };

  const loiterMin = caps.loitering_duration_min_seconds;
  const loiterMax = caps.loitering_duration_max_seconds;
  const loiterRead = data.values.getLoiteringDuration?.loitering_duration_seconds;
  const [loiter, setLoiter] = useState<number | undefined>(loiterRead);
  useEffect(() => setLoiter(loiterRead), [loiterRead]);
  const saveLoiter = useCameraAction(serial, "detection");

  const bbox = data.values.getBboxOverlay?.enabled;
  const saveBbox = useCameraAction(serial, "detection");
  const readFailed = Boolean(data.errors.getEventPreferences);
  const loiteringSupported = events.includes("Loitering") && typeof loiterMin === "number" && typeof loiterMax === "number";
  const missing = [
    ...(loiteringSupported ? [] : ["Loitering time"]),
    ...(caps.bbox_overlay_capable === true ? [] : ["Detection boxes"]),
  ];

  return (
    <>
      <Card icon={<Bell className="size-4" />} title="What the camera detects" description="Turn each detection on or off and choose what happens automatically when it fires.">
        <ReadError message={data.errors.getEventPreferences ?? data.errors.getEventResponseActions} />
        {events.length === 0 && !readFailed && <p className="text-sm text-muted-foreground">This camera does not report any detections.</p>}
        {!readFailed && <div className="divide-y divide-border">
          {events.map(event => (
            <div key={event} className="py-2">
              <SwitchRow label={eventName(event)} description={EVENT_NAMES[event]?.[1]} checked={prefs[event] ?? false} disabled={!canChange || save.isPending}
                onChange={v => setPrefs(p => ({ ...p, [event]: v }))} />
              {(prefs[event] ?? false) && (actionOptions[event]?.length ?? 0) === 0 && (
                <p className="mt-1 text-xs text-muted-foreground">This camera has no automatic responses for this detection.</p>
              )}
              {(actionOptions[event]?.length ?? 0) > 0 && (prefs[event] ?? false) && (
                <fieldset className="mt-2 flex flex-wrap gap-4 rounded-lg bg-background p-4">
                  <legend className="sr-only">When {eventName(event).toLowerCase()} fires</legend>
                  <span className="text-xs text-muted-foreground">When it fires:</span>
                  {actionOptions[event].map(action => (
                    <label key={action} className="flex items-center gap-2 text-sm">
                      <Checkbox aria-label={`${eventName(event)}: ${actionName(action)}`} disabled={!canChange || save.isPending || Boolean(data.errors.getEventResponseActions)}
                        checked={(actions[event] ?? []).includes(action)}
                        onCheckedChange={checked => setActions(a => ({ ...a, [event]: checked === true ? [...(a[event] ?? []), action] : (a[event] ?? []).filter(x => x !== action) }))} />
                      {actionName(action)}
                    </label>
                  ))}
                </fieldset>
              )}
            </div>
          ))}
        </div>}
        <Button className="mt-4" disabled={!canChange || save.isPending || !(prefsChanged || actionsChanged)} onClick={() => void apply().catch(() => {})}>
          {save.isPending && <Loader2 className="size-4 animate-spin" />}Save detection settings
        </Button>
        <SaveFeedback mutation={save} />
        <ViewerNote canChange={canChange} />
      </Card>

      {loiteringSupported && (
        <Card icon={<Bell className="size-4" />} title="Loitering time" description="How long a person must stay in view before it counts as loitering.">
          <ReadError message={data.errors.getLoiteringDuration} />
          {!data.errors.getLoiteringDuration && <LevelField label="Loitering time" unit=" seconds" value={loiter} min={loiterMin} max={loiterMax} disabled={!canChange || saveLoiter.isPending} onChange={setLoiter} />}
          <Button className="mt-4" disabled={!canChange || saveLoiter.isPending || loiter === undefined || loiter === loiterRead}
            onClick={() => saveLoiter.mutate({ op: "setLoiteringDuration", payload: { loitering_duration_seconds: loiter } })}>
            Save loitering time
          </Button>
          <SaveFeedback mutation={saveLoiter} />
        </Card>
      )}

      {caps.bbox_overlay_capable === true && (
        <Card icon={<Bell className="size-4" />} title="Detection boxes" description="Draw a box around detected people on the camera's video.">
          <ReadError message={data.errors.getBboxOverlay} />
          {!data.errors.getBboxOverlay && <SwitchRow label="Show detection boxes" checked={bbox === true} disabled={!canChange || saveBbox.isPending}
            onChange={v => saveBbox.mutate({ op: "setBboxOverlay", payload: { enabled: v } })} />}
          <SaveFeedback mutation={saveBbox} />
        </Card>
      )}

      <NotSupported items={missing} />

      {advanced(["getEventPreferences", "setEventPreferences", "getEventResponseActions", "setEventResponseActions", "getLoiteringDuration", "setLoiteringDuration", "getBboxOverlay", "setBboxOverlay"])}
    </>
  );
}

export function DetectionPanel({ serial, advanced }: PanelProps) {
  return <PanelFrame serial={serial} group="detection" title="Detection & alerts" description="Choose what the camera detects and how it responds."
    render={data => <DetectionContent serial={serial} data={data} advanced={advanced} />} />;
}

/* ------------------------------------------------------------------ Audio */

function AudioContent({ serial, cameraName, data, advanced }: { serial: string; cameraName: string; data: FeatureStateData; advanced: PanelProps["advanced"] }) {
  const canChange = useCanChange();
  const caps = data.capabilities;
  const hasMic = caps.has_microphone !== false;
  const hasSpeaker = caps.has_speaker !== false;
  // camera_api has no buzzer flag yet (requested as `buzzer_capable`); absent means unknown, so show it.
  const hasBuzzer = caps.buzzer_capable !== false;
  const levelsRead = data.values.getAudioSettings ?? {};
  const [mic, setMic] = useState<number | undefined>(levelsRead.mic_gain);
  const [speaker, setSpeaker] = useState<number | undefined>(levelsRead.speaker_volume);
  useEffect(() => { setMic(levelsRead.mic_gain); setSpeaker(levelsRead.speaker_volume); }, [levelsRead.mic_gain, levelsRead.speaker_volume]);
  const saveLevels = useCameraAction(serial, "audio");
  const levelChanges = {
    ...(hasMic && mic !== undefined && mic !== levelsRead.mic_gain ? { mic_gain: mic } : {}),
    ...(hasSpeaker && speaker !== undefined && speaker !== levelsRead.speaker_volume ? { speaker_volume: speaker } : {}),
  };

  const recording = data.values.getAudioRecording?.enabled;
  const saveRecording = useCameraAction(serial, "audio");
  const playing = data.values.getTestSoundStatus?.playing === true;
  const buzzing = data.values.getBuzzerStatus?.active === true;
  const sound = useCameraAction(serial, "audio");
  const [buzzSeconds, setBuzzSeconds] = useState(10);
  const [confirm, setConfirm] = useState<null | "test" | "buzzer">(null);

  return (
    <>
      {hasMic && (
        <Card icon={<Mic className="size-4" />} title="Microphone" description="How sensitive the camera's microphone is, and whether its audio is recorded.">
          <ReadError message={data.errors.getAudioSettings} />
          {!data.errors.getAudioSettings && <LevelField label="Microphone level" unit="%" value={mic} min={0} max={100} disabled={!canChange || saveLevels.isPending} onChange={setMic} />}
          <ReadError message={data.errors.getAudioRecording} />
          {!data.errors.getAudioRecording && <SwitchRow label="Record audio with video" checked={recording === true} disabled={!canChange || saveRecording.isPending}
            onChange={v => saveRecording.mutate({ op: "setAudioRecording", payload: { enabled: v } })} />}
          <SaveFeedback mutation={saveRecording} />
        </Card>
      )}

      {hasSpeaker && (
        <Card icon={<Volume2 className="size-4" />} title="Speaker" description="Volume for the camera's speaker, warnings and test sound.">
          <ReadError message={data.errors.getAudioSettings} />
          {!data.errors.getAudioSettings && <LevelField label="Speaker volume" unit="%" value={speaker} min={0} max={100} disabled={!canChange || saveLevels.isPending} onChange={setSpeaker} />}
          <div className="mt-4 flex flex-wrap items-center gap-4">
            {playing
              ? <Button variant="outline" disabled={!canChange || sound.isPending} onClick={() => sound.mutate({ op: "setTestSound", payload: { active: false }, confirm: true })}>Stop test sound</Button>
              : <Button variant="outline" disabled={!canChange || sound.isPending} onClick={() => setConfirm("test")}>Play test sound</Button>}
            {playing && <span role="status" className="text-sm text-muted-foreground">Test sound playing…</span>}
          </div>
        </Card>
      )}

      {(hasMic || hasSpeaker) && (
        <div className="flex flex-col gap-2">
          <Button className="self-start" disabled={!canChange || saveLevels.isPending || Object.keys(levelChanges).length === 0}
            onClick={() => saveLevels.mutate({ op: "setAudioSettings", payload: levelChanges })}>
            {saveLevels.isPending && <Loader2 className="size-4 animate-spin" />}Save audio levels
          </Button>
          <SaveFeedback mutation={saveLevels} />
          <ViewerNote canChange={canChange} />
        </div>
      )}
      <NotSupported items={[...(hasMic ? [] : ["Microphone"]), ...(hasSpeaker ? [] : ["Speaker and test sound"]), ...(hasBuzzer ? [] : ["Buzzer"])]} />

      {hasBuzzer && <Card icon={<Megaphone className="size-4" />} title="Buzzer" description="Sound the camera's built-in buzzer for a set time.">
        <ReadError message={data.errors.getBuzzerStatus} />
        <div className="flex flex-wrap items-end gap-4">
          {buzzing
            ? <Button variant="outline" disabled={!canChange || sound.isPending} onClick={() => sound.mutate({ op: "setBuzzer", payload: { active: false }, confirm: true })}>Stop buzzer</Button>
            : <>
                <label className="vms-field w-40">Duration (seconds)<Input type="number" min={1} step={1} value={buzzSeconds} disabled={!canChange} onChange={e => setBuzzSeconds(Math.max(1, Math.floor(Number(e.target.value) || 1)))} /></label>
                <Button variant="outline" disabled={!canChange || sound.isPending} onClick={() => setConfirm("buzzer")}>Sound buzzer</Button>
              </>}
          {buzzing && <span role="status" className="text-sm text-muted-foreground">Buzzer sounding…</span>}
        </div>
      </Card>}
      <SaveFeedback mutation={sound} />

      <ConfirmAction open={confirm !== null} onOpenChange={open => !open && setConfirm(null)}
        title={confirm === "buzzer" ? `Sound the buzzer on ${cameraName}?` : `Play a test sound on ${cameraName}?`}
        description="People near the camera will hear it."
        confirmLabel={confirm === "buzzer" ? "Sound buzzer" : "Play test sound"}
        onConfirm={() => {
          sound.mutate(confirm === "buzzer"
            ? { op: "setBuzzer", payload: { active: true, duration_seconds: buzzSeconds }, confirm: true }
            : { op: "setTestSound", payload: { active: true }, confirm: true });
          setConfirm(null);
        }} />

      {advanced(["getAudioSettings", "setAudioSettings", "getAudioRecording", "setAudioRecording", "getTestSoundStatus", "setTestSound", "getBuzzerStatus", "setBuzzer"])}
    </>
  );
}

export function AudioPanel({ serial, cameraName, advanced }: PanelProps) {
  return <PanelFrame serial={serial} group="audio" title="Audio" description="Microphone, speaker and buzzer."
    render={data => <AudioContent serial={serial} cameraName={cameraName} data={data} advanced={advanced} />} />;
}

/* ------------------------------------------------------------------ Siren & spotlight */

const OUTPUTS = [
  { action: "siren", label: "Siren", icon: <Siren className="size-4" />, field: "siren_seconds", unit: "seconds" },
  { action: "spotlight", label: "Spotlight", icon: <Sun className="size-4" />, field: "spotlight_seconds", unit: "seconds" },
  { action: "warning", label: "Voice warning", icon: <Megaphone className="size-4" />, field: "warning_repeat_count", unit: "repeats" },
] as const;

function DeterrenceContent({ serial, cameraName, data, advanced }: { serial: string; cameraName: string; data: FeatureStateData; advanced: PanelProps["advanced"] }) {
  const canChange = useCanChange();
  const caps = data.capabilities;
  const outputs = OUTPUTS.filter(o => caps[`${o.action}_capable`] === true);
  const status = data.values.getDeterrenceStatus ?? {};
  const toggle = useCameraAction(serial, "deterrence");
  const [confirm, setConfirm] = useState<(typeof OUTPUTS)[number] | null>(null);

  const ranges = data.values.getDeterrenceDurationOptions ?? {};
  const durationsRead = data.values.getDeterrenceDurations ?? {};
  const [durations, setDurations] = useState<Record<string, number>>({});
  useEffect(() => setDurations({ ...durationsRead }), [durationsRead]);
  const saveDurations = useCameraAction(serial, "deterrence");
  const editable = outputs.filter(o => typeof ranges[`${o.field}_min`] === "number" && typeof ranges[`${o.field}_max`] === "number");
  const changes = Object.fromEntries(editable.filter(o => durations[o.field] !== undefined && durations[o.field] !== durationsRead[o.field]).map(o => [o.field, durations[o.field]]));

  const missingOutputs = OUTPUTS.filter(o => !outputs.includes(o)).map(o => o.label);
  if (outputs.length === 0) return <>
    <p className="rounded-xl border border-border bg-card p-8 text-muted-foreground">This camera has no siren, spotlight or voice warning.</p>
    {advanced(["getDeterrenceStatus", "setDeterrence", "getDeterrenceDurations", "setDeterrenceDurations", "getDeterrenceDurationOptions"])}
  </>;

  return (
    <>
      <Card icon={<Siren className="size-4" />} title="Turn on now" description="Switch an output on by hand. It stops by itself after its automatic stop time.">
        <ReadError message={data.errors.getDeterrenceStatus} />
        <div className="grid gap-4 sm:grid-cols-3">
          {outputs.map(o => {
            const on = status[o.action] === true;
            return (
              <div key={o.action} className="flex flex-col gap-2 rounded-lg border border-border p-4">
                <span className="flex items-center gap-2 text-sm font-semibold">{o.icon}{o.label}</span>
                <span className={on ? "text-sm text-warning" : "text-sm text-muted-foreground"}>{data.errors.getDeterrenceStatus ? "Status unknown" : on ? "On" : "Off"}</span>
                <Button variant={on ? "default" : "outline"} size="sm" disabled={!canChange || toggle.isPending}
                  onClick={() => on ? toggle.mutate({ op: "setDeterrence", payload: { action: o.action, active: false }, confirm: true }) : setConfirm(o)}>
                  {on ? `Turn off ${o.label.toLowerCase()}` : `Turn on ${o.label.toLowerCase()}`}
                </Button>
              </div>
            );
          })}
        </div>
        <SaveFeedback mutation={toggle} />
        <ViewerNote canChange={canChange} />
      </Card>

      {editable.length > 0 && (
        <Card icon={<RefreshCw className="size-4" />} title="Automatic stop times" description="How long each output runs when it is triggered, by hand or by a detection.">
          <ReadError message={data.errors.getDeterrenceDurations ?? data.errors.getDeterrenceDurationOptions} />
          {!data.errors.getDeterrenceDurations && <div className="grid gap-4 sm:grid-cols-3">
            {editable.map(o => (
              <LevelField key={o.field} label={`${o.label} (${o.unit})`} value={durations[o.field]} min={ranges[`${o.field}_min`]} max={ranges[`${o.field}_max`]}
                disabled={!canChange || saveDurations.isPending} onChange={v => setDurations(d => ({ ...d, [o.field]: v }))} />
            ))}
          </div>}
          <Button className="mt-4" disabled={!canChange || saveDurations.isPending || Object.keys(changes).length === 0}
            onClick={() => saveDurations.mutate({ op: "setDeterrenceDurations", payload: changes })}>
            Save stop times
          </Button>
          <SaveFeedback mutation={saveDurations} />
        </Card>
      )}

      <NotSupported items={missingOutputs} />

      <ConfirmAction open={confirm !== null} onOpenChange={open => !open && setConfirm(null)}
        title={`Turn on the ${confirm?.label.toLowerCase()} on ${cameraName}?`}
        description="People near the camera will see or hear it."
        confirmLabel={`Turn on ${confirm?.label.toLowerCase() ?? ""}`}
        onConfirm={() => { if (confirm) toggle.mutate({ op: "setDeterrence", payload: { action: confirm.action, active: true }, confirm: true }); setConfirm(null); }} />

      {advanced(["getDeterrenceStatus", "setDeterrence", "getDeterrenceDurations", "setDeterrenceDurations", "getDeterrenceDurationOptions"])}
    </>
  );
}

export function DeterrencePanel({ serial, cameraName, advanced }: PanelProps) {
  return <PanelFrame serial={serial} group="deterrence" title="Siren & spotlight" description="Deter intruders by hand, and set how long each output runs."
    render={data => <DeterrenceContent serial={serial} cameraName={cameraName} data={data} advanced={advanced} />} />;
}
