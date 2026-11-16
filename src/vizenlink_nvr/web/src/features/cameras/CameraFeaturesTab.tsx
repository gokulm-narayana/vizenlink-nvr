import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw, ShieldCheck, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { InlineError } from "@/components/InlineError";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { CameraAccountsTab } from "./CameraAccountsTab";
import { PrivacyZones } from "./PrivacyZones";
import { AudioPanel, DetectionPanel, DeterrencePanel } from "./CameraControlPanels";

export const CAMERA_FEATURE_TABS = [
  { id: "privacy", title: "Privacy" }, { id: "detection", title: "Detection & alerts" },
  { id: "audio", title: "Audio" }, { id: "camera-storage", title: "Camera SD card" },
  { id: "deterrence", title: "Siren & spotlight" }, { id: "movement", title: "Movement protection" },
  { id: "accounts", title: "Camera accounts" }, { id: "network", title: "Network" }, { id: "connections", title: "Camera connections" },
];
export interface Schema { type?: string; properties?: Record<string, Schema>; additionalProperties?: Schema | boolean; items?: Schema; enum?: Array<string | number | boolean>; required?: string[]; minimum?: number; maximum?: number; default?: unknown; description?: string }
interface Operation { id: string; method: string; path: string; schema: Schema; query: Record<string, Schema>; read_only: boolean; owner_only: boolean; confirmation_required: boolean; capability?: string }
interface FeatureState { title: string; description: string; source: string; capabilities: Record<string, any>; values: Record<string, Record<string, any>>; errors: Record<string, string>; operations: Operation[] }

function previewOperationPair(name: string, path: string, schema: Schema): Operation[] {
  const defaults = { path, query: {}, owner_only: false, confirmation_required: false };
  return [
    { ...defaults, id: `get${name}`, method: "GET", schema: { type: "object" }, read_only: true },
    { ...defaults, id: `set${name}`, method: "POST", schema, read_only: false },
  ];
}

const DETECTION_PREVIEW: FeatureState = {
  title: "Detection & alerts",
  description: "Choose which events to detect and what happens when they’re detected.",
  source: "Preview",
  capabilities: {
    supported_event_types: ["PersonDetected", "Loitering", "Tamper"],
    supported_event_deterrence_options: { PersonDetected: ["mobile_alert", "spotlight"], Loitering: ["mobile_alert"], Tamper: ["mobile_alert", "siren"] },
    loitering_duration_min_seconds: 10,
    loitering_duration_max_seconds: 90,
  },
  values: {
    getEventPreferences: { PersonDetected: true, Loitering: false, Tamper: true },
    getEventResponseActions: { PersonDetected: ["mobile_alert"], Loitering: [], Tamper: ["mobile_alert"] },
    getLoiteringDuration: { loitering_duration_seconds: 30 },
    getBboxOverlay: { enabled: true },
  },
  errors: {},
  operations: [
    ...previewOperationPair("EventPreferences", "/preferences", { type: "object" }),
    ...previewOperationPair("EventResponseActions", "/response-actions", { type: "object" }),
    ...previewOperationPair("LoiteringDuration", "/loitering-duration", {
      type: "object", properties: { loitering_duration_seconds: { type: "integer" } },
    }),
    ...previewOperationPair("BboxOverlay", "/bbox-overlay", {
      type: "object", properties: { enabled: { type: "boolean" } },
    }),
  ],
};
const TITLES: Record<string, string> = {
  setPrivacyMode: "Privacy mode", getPrivacyMode: "Privacy mode", setEventPreferences: "Event detection", setEventResponseActions: "Automatic responses", setLoiteringDuration: "Loitering duration", setBboxOverlay: "Detection boxes", queryAlertRule: "Read a detection rule", setAlertRule: "Rule notifications", setAudioSettings: "Microphone & speaker", setAudioRecording: "Record camera audio", setTestSound: "Speaker test", setBuzzer: "Buzzer", setLocalStorage: "Camera SD recording", setRecordingMode: "SD recording mode & schedule", setRecordingClipDuration: "SD clip duration", getRecordings: "Browse camera recordings", getRecordingDates: "Dates with SD footage", deleteRecordings: "Delete camera recordings", setDeterrence: "Manual deterrence", setDeterrenceDurations: "Automatic stop times", getDeterrenceDurationOptions: "Supported stop-time ranges", setMovementProtectionSensitivity: "Movement sensitivity", calibrateMovementProtection: "Calibrate camera position", setWifi: "Wi-Fi connection", getWifiSignal: "Wireless signal", getTimezones: "Supported time zones", getCapabilities: "Camera capabilities", getDeviceHealth: "Live device health", getVideoMode: "Day / night status", getImageDefaults: "Factory image defaults", setNightVisionType: "Night vision type", setMirrorFlip: "Mirror / flip", setAntiFlickerMode: "Anti-flicker", getLiveStreamUri: "Live connection details", getTalkUri: "Talk connection details", stopCloudStreaming: "Stop camera cloud stream", getCloudStreamingStatus: "Camera cloud stream status",
};
const WORDS: Record<string, string> = { psk: "Wi-Fi password", mic_gain: "Microphone gain", speaker_volume: "Speaker volume", ssid: "Network name (SSID)", enabled: "Enabled", active: "Active", verify: "Connect and verify before saving", start: "From (UTC epoch seconds)", end: "Through (UTC epoch seconds)", tz_offset_minutes: "Time-zone offset in minutes", ids: "Recording IDs", delete_all: "Delete every recording on the SD card", profile_token: "Stream profile", day_of_week: "Day", start_minute: "Start time", end_minute: "End time" };
export function fieldLabel(key: string): string { return WORDS[key] || key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ").replace(/^./, v => v.toUpperCase()); }

function emptyValue(schema: Schema): any {
  if (schema.default !== undefined) return schema.default;
  if (schema.type === "object") return Object.fromEntries(Object.entries(schema.properties || {}).filter(([key]) => schema.required?.includes(key)).map(([key, field]) => [key, emptyValue(field)]));
  if (schema.type === "array") return [];
  if (schema.type === "boolean") return false;
  return "";
}

function adaptSchema(op: Operation, caps: Record<string, any>, ranges: Record<string, any>): Schema {
  const schema: Schema = JSON.parse(JSON.stringify(op.schema));
  const properties = schema.properties || {};
  if (op.id === "setEventPreferences" || op.id === "setEventResponseActions") {
    schema.properties = Object.fromEntries((op.id === "setEventResponseActions" ? Object.keys(caps.supported_event_deterrence_options || {}) : caps.supported_event_types || []).map((event: string) => [event, op.id === "setEventPreferences" ? { type: "boolean" } : { type: "array", items: { type: "string", enum: caps.supported_event_deterrence_options?.[event] || [] } }]));
    schema.additionalProperties = false;
  }
  if (op.id === "setMovementProtectionSensitivity" && properties.sensitivity) properties.sensitivity.enum = caps.supported_movement_sensitivities || [];
  if (op.id === "setRecordingMode" && properties.mode) properties.mode.enum = caps.supported_recording_modes || [];
  if (op.id === "setDeterrence" && properties.action) properties.action.enum = ["siren", "spotlight", "warning"].filter(a => caps[`${a}_capable`] === true);
  if (op.id === "setNightVisionType" && properties.type) properties.type.enum = ["Grey", ...(caps.night_vision_color_capable ? ["Color"] : []), ...(caps.night_vision_smart_capable ? ["Smart"] : [])];
  for (const [id, field, prefix] of [["setLoiteringDuration", "loitering_duration_seconds", "loitering_duration"], ["setRecordingClipDuration", "clip_duration_seconds", "recording_clip_duration"]]) {
    if (op.id === id && properties[field]) { properties[field].minimum = caps[`${prefix}_min_seconds`]; properties[field].maximum = caps[`${prefix}_max_seconds`]; }
  }
  if (op.id === "setDeterrenceDurations") {
    for (const key of Object.keys(properties)) {
      if (caps[`${key.split("_")[0]}_capable`] !== true || ranges[`${key}_min`] === undefined || ranges[`${key}_max`] === undefined) delete properties[key];
      else { properties[key].minimum = ranges[`${key}_min`]; properties[key].maximum = ranges[`${key}_max`]; }
    }
  }
  if (op.id === "setAudioSettings") {
    if (caps.has_microphone === false) delete properties.mic_gain;
    if (caps.has_speaker === false) delete properties.speaker_volume;
  }
  return schema;
}

export function SchemaFields({ schema, value, onChange, name = "settings", label = "Settings" }: { schema: Schema; value: any; onChange: (value: any) => void; name?: string; label?: string }) {
  if (schema.type === "object") return <div className="grid gap-4 sm:grid-cols-2">{Object.entries(schema.properties || {}).map(([key, field]) => <div key={key} className={field.type === "array" || field.type === "object" ? "sm:col-span-2" : ""}><SchemaFields schema={field} value={value?.[key]} label={fieldLabel(key)} name={`${name}.${key}`} onChange={next => { const updated = { ...value }; if (next === "" || next === undefined) delete updated[key]; else updated[key] = next; onChange(updated); }} /></div>)}</div>;
  if (schema.type === "array") {
    const values: any[] = Array.isArray(value) ? value : [];
    if (schema.items?.enum) return <fieldset className="flex flex-col gap-2 rounded-lg border border-border p-4"><legend className="px-2 text-sm font-semibold">{label}</legend>{schema.items.enum.map(option => <label key={String(option)} className="flex items-center gap-2 text-sm"><Checkbox checked={values.includes(option)} onCheckedChange={checked => onChange(checked === true ? [...values, option] : values.filter(v => v !== option))} />{fieldLabel(String(option))}</label>)}{schema.items.enum.length === 0 && <p className="text-xs text-muted-foreground">No automatic response actions reported for this event.</p>}</fieldset>;
    return <fieldset className="flex flex-col gap-4 rounded-lg border border-border p-4"><legend className="px-2 text-sm font-semibold">{label}</legend>{values.map((item, i) => <div key={i} className="flex items-start gap-2"><div className="min-w-0 flex-1"><SchemaFields schema={schema.items || { type: "string" }} value={item} onChange={next => onChange(values.map((v, j) => j === i ? next : v))} name={`${name}.${i}`} label={`${label} ${i + 1}`} /></div><Button type="button" variant="ghost" size="icon" aria-label={`Remove ${label} ${i + 1}`} onClick={() => onChange(values.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button></div>)}<Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...values, emptyValue(schema.items || { type: "string" })])}><Plus className="size-4" />Add {label.toLowerCase()}</Button></fieldset>;
  }
  if (schema.type === "boolean") return <label className="flex min-h-10 items-center gap-2 text-sm"><Checkbox aria-label={label}  checked={value === true} onCheckedChange={checked => onChange(checked === true)} />{label}</label>;
  if (schema.enum) return <label className="vms-field"><span>{label}</span><NativeSelect aria-label={label} className="w-full" value={value === undefined ? "" : String(value)} onChange={e => onChange(schema.enum!.find(v => String(v) === e.target.value) ?? "")}><option value="">Choose…</option>{schema.enum.map(option => <option key={String(option)} value={String(option)}>{fieldLabel(String(option))}</option>)}</NativeSelect></label>;
  if (name.endsWith(".day_of_week")) return <label className="vms-field">{label}<NativeSelect value={value ?? ""} onChange={e => onChange(Number(e.target.value))}><option value="">Choose day…</option>{["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].map((d, i) => <option key={d} value={i}>{d}</option>)}</NativeSelect></label>;
  if (name.endsWith("_minute")) return <label className="vms-field">{label}<Input type="time" value={typeof value === "number" ? `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}` : ""} onChange={e => { const [h, m] = e.target.value.split(":").map(Number); onChange(Number.isFinite(h + m) ? h * 60 + m : ""); }} /></label>;
  if (name === "query.start" || name === "query.end") {
    const local = typeof value === "number" ? new Date(value * 1000 - new Date(value * 1000).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
    return <label className="vms-field">{name.endsWith("start") ? "From (local time)" : "Through (local time)"}<Input type="datetime-local" value={local} onChange={e => onChange(e.target.value ? Math.floor(new Date(e.target.value).getTime() / 1000) : "")} /></label>;
  }
  const numeric = schema.type === "integer" || schema.type === "number";
  return <label className="vms-field"><span>{label}</span><Input aria-label={label} type={name.endsWith(".psk") ? "password" : numeric ? "number" : "text"} autoComplete="off" min={schema.minimum} max={schema.maximum} step={schema.type === "integer" ? 1 : numeric ? "any" : undefined} value={value ?? ""} onChange={e => onChange(numeric && e.target.value !== "" ? Number(e.target.value) : e.target.value)} />{(schema.minimum !== undefined || schema.maximum !== undefined) && <span className="text-xs text-muted-foreground">Supported range: {schema.minimum ?? "—"}–{schema.maximum ?? "—"}</span>}</label>;
}

function StatusValues({ value, depth = 0 }: { value: any; depth?: number }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">Not reported</span>;
  if (typeof value !== "object") return <span className="break-all text-sm">{typeof value === "boolean" ? value ? "Yes" : "No" : String(value)}</span>;
  if (depth > 3) return <span className="text-xs text-muted-foreground">Additional camera metadata</span>;
  return <dl className="grid gap-2 text-sm">{Object.entries(value).slice(0, 250).map(([key, item]) => <div key={key} className="min-w-0 rounded-lg bg-background p-2"><dt className="mb-1 text-xs font-semibold text-muted-foreground">{fieldLabel(key)}</dt><dd><StatusValues value={item} depth={depth + 1} /></dd></div>)}</dl>;
}

function CameraRecordingResults({ serial, output }: { serial: string; output: Record<string, any> }) {
  const [playing, setPlaying] = useState<number | null>(null);
  const clips = Array.isArray(output.recordings) ? output.recordings : [];
  const url = (id: number) => `/api/v1/cameras/${encodeURIComponent(serial)}/sd-recordings/${id}/clip`;
  return <div className="flex flex-col gap-4">
    {output.truncated && <p className="text-sm text-warning">More clips are available. Narrow the date range to see them.</p>}
    {playing !== null && <video key={playing} src={url(playing)} controls preload="metadata" className="aspect-video w-full rounded-xl bg-video-bg" aria-label="Camera SD recording player" />}
    {clips.length === 0 && <p className="text-sm text-muted-foreground">{output.card_present === false ? "No SD card is present in this camera." : "No camera recordings found in this range."}</p>}
    {clips.slice(0, 250).map((clip: any) => <div key={clip.id} className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border p-4"><div><p className="text-sm font-semibold">{typeof clip.start === "number" ? new Date(clip.start * 1000).toLocaleString() : `Recording ${clip.id}`}</p><p className="mt-1 text-xs text-muted-foreground">ID {clip.id} · {clip.active ? "Currently recording" : `${Math.max(0, (clip.end || 0) - (clip.start || 0))} seconds`} · {Math.round((clip.size_bytes || 0) / 1024)} KB{clip.trigger ? ` · ${fieldLabel(clip.trigger)}` : ""}</p></div><div className="flex items-center gap-4"><Button type="button" variant="outline" size="sm" onClick={() => setPlaying(clip.id)}>Play SD clip</Button>{!clip.active && <a href={`${url(clip.id)}?download=true`} className="text-sm font-semibold text-primary-text">Download SD clip</a>}</div></div>)}
  </div>;
}

function OperationCard({ op, read, state, serial, cameraName, reload, preview = false }: { op: Operation; read?: Operation; state: FeatureState; serial: string; cameraName: string; reload: () => void; preview?: boolean }) {
  const user = useCurrentUser();
  const [pendingConfirm, setPendingConfirm] = useState(false);
  const [confirmedName, setConfirmedName] = useState("");
  const [previewValue, setPreviewValue] = useState<Record<string, unknown> | null>(null);
  const current = previewValue ?? state.values[read?.id || op.id] ?? {};
  const schema = useMemo(() => adaptSchema(op, state.capabilities, state.values.getDeterrenceDurationOptions || {}), [op, state.capabilities, current]);
  const [payload, setPayload] = useState<Record<string, any>>({});
  const [query, setQuery] = useState<Record<string, any>>({});
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const initial = Object.fromEntries(Object.keys(schema.properties || {}).filter(k => current[k] !== undefined && k !== "psk").map(k => [k, current[k]]));
    if (op.id === "setEventPreferences" || op.id === "setEventResponseActions") Object.assign(initial, current);
    setPayload(initial); setDirty(false);
  }, [state.values, op.id]);
  const queryClient = useQueryClient();
  const mutation = useMutation({ gcTime: 0, mutationFn: (confirmation?: string) => apiFetch<{ output: Record<string, any> }>(`/api/v1/cameras/${encodeURIComponent(serial)}/features/actions/${op.id}`, { method: "POST", body: { payload, query, confirmation } }) });
  const allowed = preview || op.read_only || user?.role === "owner" || user?.role === "operator" && !op.owner_only;
  const run = async (confirmed = false) => {
    if (preview) {
      setPreviewValue(payload);
      setDirty(false);
      return;
    }
    if (op.confirmation_required && !confirmed) { setConfirmedName(""); setPendingConfirm(true); return; }
    try { await mutation.mutateAsync(confirmed ? serial : undefined); setDirty(false); setPendingConfirm(false); setPayload(prev => { const next = { ...prev }; delete next.psk; return next; }); if (!op.read_only) { void queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] }); reload(); } }
    catch { setPendingConfirm(false); }
  };
  const title = TITLES[op.id] || fieldLabel(op.id);
  const readError = state.errors[read?.id || op.id];
  const hasFields = Object.keys(schema.properties || {}).length > 0;
  return <section className="min-w-0 rounded-xl border border-border bg-card p-6">
    <div className="mb-4 flex items-center justify-between gap-2"><h3 className="font-semibold">{title}</h3>{op.owner_only && <span className="text-xs text-muted-foreground">Owner only</span>}</div>
    {readError && <p role="alert" className="mb-4 rounded-lg bg-warning-subtle p-4 text-sm text-warning">{readError}</p>}
    {op.id === "getTalkUri" && <p className="mb-4 text-sm text-muted-foreground">This reads the camera's talk transport information. Sending microphone audio requires a compatible RTSPS audio bridge.</p>}
    {Object.keys(current).length > 0 && <details className="mb-4" open={op.read_only}><summary className="cursor-pointer text-sm text-primary-text">{preview ? "Preview values" : "Current camera values"}</summary><div className="mt-2 max-h-80 overflow-auto"><StatusValues value={current} /></div></details>}
    {(!op.read_only || hasFields || Object.keys(op.query).length > 0) && <form className="flex flex-col gap-4" onSubmit={e => { e.preventDefault(); void run(); }}>
      <SchemaFields schema={schema} value={payload} onChange={next => { setPayload(next); setDirty(true); }} />
      {Object.keys(op.query).length > 0 && <SchemaFields schema={{ type: "object", properties: op.query }} value={query} name="query" onChange={setQuery} />}
      <Button type="submit" className="self-start" disabled={!allowed || mutation.isPending || !op.read_only && !dirty && hasFields}>{mutation.isPending && <Loader2 className="size-4 animate-spin" />}{preview ? `Preview ${title.toLowerCase()} change` : op.read_only ? "Read from camera" : `Apply ${title.toLowerCase()}`}</Button>
    </form>}
    {op.read_only && !hasFields && !Object.keys(op.query).length && <Button variant="outline" size="sm" disabled={mutation.isPending} onClick={() => void run()}><RefreshCw className="size-4" />Read from camera</Button>}
    {!allowed && <p className="mt-2 text-xs text-muted-foreground">{op.owner_only ? "Only the NVR owner can change this setting." : "Ask an operator or owner to change this setting."}</p>}
    {mutation.error && <p role="alert" className="mt-4 rounded-lg bg-critical-subtle p-4 text-sm text-critical">{mutation.error.message}</p>}
    {previewValue && !dirty && <p role="status" className="mt-4 text-sm text-muted-foreground">Preview updated for this session.</p>}
    {mutation.isSuccess && <div className="mt-4"><p role="status" className="mb-2 flex items-center gap-2 text-sm text-success"><Check className="size-4" />{op.read_only ? "Read from camera" : "Camera confirmed the change"}</p>{mutation.data?.output && <div className="max-h-80 overflow-auto">{op.id === "getRecordings" ? <CameraRecordingResults serial={serial} output={mutation.data.output} /> : <StatusValues value={mutation.data.output} />}</div>}</div>}
    <Dialog open={pendingConfirm} onOpenChange={setPendingConfirm}><DialogContent><DialogHeader><DialogTitle>Confirm {title.toLowerCase()}</DialogTitle><DialogDescription>{op.id === "deleteRecordings" ? "This permanently deletes footage from the camera SD card. It cannot be undone." : op.id === "setWifi" ? "Changing Wi-Fi can disconnect this camera from the NVR and interrupt recording." : op.id === "setPrivacyMode" ? "Full privacy stops video and audio capture and interrupts recording. Zone mode uses the camera's configured masks." : "This changes the camera's physical state or configuration. Review the selected values before applying."}</DialogDescription></DialogHeader><p className="text-sm font-semibold">Camera: {cameraName}</p><StatusValues value={Object.fromEntries(Object.entries(payload).filter(([key]) => key !== "psk"))} /><label className="vms-field">Type the camera name to confirm<Input aria-label="Confirm camera name" value={confirmedName} onChange={e => setConfirmedName(e.target.value)} /></label><Button disabled={confirmedName !== cameraName || mutation.isPending} onClick={() => void run(true)}>Confirm camera action</Button></DialogContent></Dialog>
  </section>;
}

interface CameraFeatureProps {
  serial: string;
  cameraName: string;
  group: string;
}

function FeatureCards({ serial, cameraName, group, data, reload, preview = false }: CameraFeatureProps & {
  data: FeatureState;
  reload: () => void;
  preview?: boolean;
}) {
  const operations = data.operations.filter(op => !op.capability || data.capabilities[op.capability] === true);
  const writes = operations.filter(op => !op.read_only);
  const cards = operations.filter(op => !op.read_only || !writes.some(w => w.path === op.path && op.method === "GET"));

  if (!cards.length) return <p className="rounded-xl border border-border bg-card p-8 text-muted-foreground">This camera does not report support for this feature.</p>;
  return (
    <div className="grid min-w-0 gap-4">
      {cards.map(op => <OperationCard key={`${serial}-${group}-${op.id}`} op={op}
        read={operations.find(r => r.method === "GET" && r.path === op.path)} state={data}
        serial={serial} cameraName={cameraName} reload={reload} preview={preview} />)}
    </div>
  );
}

function RestCameraFeaturesTab({ serial, cameraName, group }: CameraFeatureProps) {
  const state = useQuery({ queryKey: ["cameraFeatures", serial, group], queryFn: ({ signal }) => apiFetch<FeatureState>(`/api/v1/cameras/${encodeURIComponent(serial)}/features/${group}`, { signal }), retry: false, staleTime: 30000 });
  if (state.isPending) return <div className="flex items-center gap-2 rounded-xl border border-border bg-card p-8 text-sm"><Loader2 className="size-4 animate-spin" />Reading supported settings from the camera…</div>;
  if (state.error) return <InlineError message={state.error.message} actionLabel="Reload camera features" onAction={() => void state.refetch()} />;
  const data = state.data!;
  return <div className="flex flex-col gap-6"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="text-xl font-semibold">{data.title}</h2><p className="mt-2 text-sm text-muted-foreground">{data.description}</p></div><Button variant="outline" disabled={state.isFetching} onClick={() => void state.refetch()}><RefreshCw className="size-4" />Refresh camera values</Button></div><div className="flex items-start gap-2 rounded-xl bg-selected p-4 text-sm text-selected-foreground"><ShieldCheck className="mt-1 size-4 shrink-0" /><p>Values and supported choices come from this camera. Changes apply to the camera itself.</p></div><FeatureCards serial={serial} cameraName={cameraName} group={group} data={data} reload={() => void state.refetch()} />{group === "privacy" && <PrivacyZones serial={serial} cameraName={cameraName} />}</div>;
}

/** Generic forms for the operations a hand-built screen does not cover (e.g. named alert rules). */
function MoreCameraOptions({ serial, cameraName, group, handled }: CameraFeatureProps & { handled: string[] }) {
  const state = useQuery({ queryKey: ["cameraFeatures", serial, group], queryFn: ({ signal }) => apiFetch<FeatureState>(`/api/v1/cameras/${encodeURIComponent(serial)}/features/${group}`, { signal }), retry: false, staleTime: 30000 });
  if (!state.data) return null;
  const rest = { ...state.data, operations: state.data.operations.filter(op => !handled.includes(op.id) && (!op.capability || state.data.capabilities[op.capability] === true)) };
  if (!rest.operations.length) return null;
  return <details className="rounded-xl border border-border bg-card p-6"><summary className="cursor-pointer text-sm font-semibold">More camera options</summary><div className="mt-4"><FeatureCards serial={serial} cameraName={cameraName} group={group} data={rest} reload={() => void state.refetch()} /></div></details>;
}

const HAND_BUILT: Record<string, typeof DetectionPanel> = { detection: DetectionPanel, audio: AudioPanel, deterrence: DeterrencePanel };

export function CameraFeaturesTab({ preview = false, ...props }: CameraFeatureProps & { preview?: boolean }) {
  if (props.group === "accounts") return <CameraAccountsTab serial={props.serial} cameraName={props.cameraName} />;
  const Panel = HAND_BUILT[props.group];
  if (Panel && !preview) return <Panel serial={props.serial} cameraName={props.cameraName} advanced={handled => <MoreCameraOptions {...props} handled={handled} />} />;
  if (props.group === "detection" && preview) return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-selected p-4 text-selected-foreground">
        <h2 className="text-xl font-semibold">Detection & alerts preview</h2>
        <p className="mt-2 text-sm">Try these controls with sample camera settings. Changes stay on this page until you leave or reload.</p>
      </div>
      <FeatureCards {...props} data={DETECTION_PREVIEW} reload={() => {}} preview />
    </div>
  );
  return <RestCameraFeaturesTab {...props} />;
}
