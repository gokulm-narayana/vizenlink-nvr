import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Save, Trash2, ImageOff, ShieldAlert, ShieldCheck } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { InlineError } from "@/components/InlineError";

export interface ZoneRect { x: number; y: number; width: number; height: number }
interface Point { x: number; y: number }
interface ZoneDraft { polygon: Point[]; enabled: boolean; type: string }
interface Mask extends ZoneDraft { token: string }
interface MaskState { masks: Mask[]; options: { max_masks: number; types: string[]; rectangle_only: boolean } }
type ZoneChange = { token: string; draft: ZoneDraft } | { token: string; draft?: undefined };
type ZonePreviewKind = "privacy" | "person";
/** What the camera reports for privacy mode. Zones only hide video in "Zone". */
type PrivacyMode = "None" | "Zone" | "Full";
export function rectToPolygon(rect: ZoneRect): Point[] {
  const x = rect.x / 50 - 1, y = 1 - rect.y / 50;
  return [{ x, y }, { x: x + rect.width / 50, y }, { x: x + rect.width / 50, y: y - rect.height / 50 }, { x, y: y - rect.height / 50 }];
}
export function polygonToRect(points: Point[]): ZoneRect {
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  return { x: (Math.min(...xs) + 1) * 50, y: (1 - Math.max(...ys)) * 50, width: (Math.max(...xs) - Math.min(...xs)) * 50, height: (Math.max(...ys) - Math.min(...ys)) * 50 };
}
const DEFAULT_RECT = { x: 25, y: 25, width: 30, height: 30 };
/** Selection value for a zone that is drawn but not yet on the camera. */
const NEW = "new";
/** A drag smaller than this (percent of the picture) is a click, not a new rectangle. */
const MIN_DRAG = 2;

export function PrivacyZones({ serial, cameraName }: { serial: string; cameraName: string }) {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const allowed = user?.role === "owner" || user?.role === "operator";
  const root = `/api/v1/cameras/${encodeURIComponent(serial)}/features`;
  const base = `${root}/privacy/masks`;
  const state = useQuery({ queryKey: ["cameraMasks", serial], queryFn: () => apiFetch<MaskState>(base), retry: false, staleTime: 30000 });
  // Same query key as the Privacy tab above, so this reuses its answer instead of asking the camera again.
  const feature = useQuery({ queryKey: ["cameraFeatures", serial, "privacy"], queryFn: ({ signal }) => apiFetch<{ values?: Record<string, { mode?: string }> }>(`${root}/privacy`, { signal }), retry: false, staleTime: 30000 });
  if (state.isPending) return <p className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">Reading the camera's privacy-zone options…</p>;
  if (state.error) return <InlineError message={state.error.message} actionLabel="Reload privacy zones" onAction={() => void state.refetch()} />;
  if (!state.data.options.max_masks) return <p className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">This camera does not report support for privacy zones.</p>;

  async function changeZone({ token, draft }: ZoneChange) {
    const path = token ? `${base}/${encodeURIComponent(token)}` : base;
    let saved = token;
    if (draft) saved = (await apiFetch<{ token?: string }>(path, { method: token ? "PUT" : "POST", body: draft }))?.token || token;
    else await apiFetch(path, { method: "DELETE" });
    await state.refetch();
    return saved;
  }

  async function turnOnZoneMode() {
    await apiFetch(`${root}/actions/setPrivacyMode`, { method: "POST", body: { payload: { mode: "Zone" }, query: {}, confirmation: serial } });
    await queryClient.invalidateQueries({ queryKey: ["cameraFeatures", serial] });
  }

  const reported = feature.data?.values?.getPrivacyMode?.mode;
  const mode = reported === "None" || reported === "Zone" || reported === "Full" ? reported : undefined;
  return <ZoneEditor key={serial} serial={serial} cameraName={cameraName} allowed={allowed} data={state.data} mode={mode} onChange={changeZone} onTurnOnZoneMode={turnOnZoneMode} />;
}

export function ZonePreview({ kind }: { kind: ZonePreviewKind }) {
  const [zones, setZones] = useState<Mask[]>([]);
  const nextId = useRef(1);
  const data: MaskState = {
    masks: zones,
    options: { max_masks: 4, types: kind === "privacy" ? ["Color"] : [], rectangle_only: true },
  };

  async function changeZone({ token, draft }: ZoneChange) {
    if (!draft) {
      setZones(current => current.filter(zone => zone.token !== token));
      return token;
    }
    const zone = { ...draft, token: token || `preview-${nextId.current++}` };
    setZones(current => token ? current.map(item => item.token === token ? zone : item) : [...current, zone]);
    return zone.token;
  }

  return <ZoneEditor allowed data={data} preview={kind} onChange={changeZone} />;
}

interface ZoneEditorProps {
  serial?: string;
  cameraName?: string;
  allowed: boolean;
  data: MaskState;
  preview?: ZonePreviewKind;
  mode?: PrivacyMode;
  onChange: (change: ZoneChange) => Promise<string>;
  onTurnOnZoneMode?: () => Promise<void>;
}

function ZoneEditor({ serial, cameraName, allowed, data, preview, mode, onChange, onTurnOnZoneMode }: ZoneEditorProps) {
  const { masks, options } = data;
  const person = preview === "person";
  const zoneLabel = person ? "person detection zone" : "privacy zone";
  const first = masks[0];
  // "" = nothing selected, NEW = a zone that is not on the camera yet, otherwise a camera zone token.
  const [selected, setSelected] = useState(first ? first.token : preview ? NEW : "");
  const [draft, setDraft] = useState<ZoneRect>(first ? polygonToRect(first.polygon) : DEFAULT_RECT);
  const [type, setType] = useState(first?.type || options.types[0] || "");
  const [enabled, setEnabled] = useState(first?.enabled ?? true);
  const [dirty, setDirty] = useState(!first && Boolean(preview));
  const [imageError, setImageError] = useState(false);
  const [imageVersion, setImageVersion] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [confirmingMode, setConfirmingMode] = useState(false);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ start: Point; rect: ZoneRect; mode: string; wasSelected: string; wasDirty: boolean } | null>(null);
  const isNew = selected === NEW;
  const full = masks.length >= options.max_masks;
  const refreshImage = () => { setImageError(false); setImageVersion(Date.now()); };

  const choose = (mask?: Mask) => {
    mutation.reset();
    setSelected(mask ? mask.token : NEW);
    setDraft(mask ? polygonToRect(mask.polygon) : DEFAULT_RECT);
    setType(mask?.type || options.types[0] || "");
    setEnabled(mask?.enabled ?? true);
    setDirty(!mask);
  };
  const mutation = useMutation({
    mutationFn: onChange,
    onSuccess: (token, change) => {
      setDeleting(false);
      refreshImage();
      if (change.draft) { setSelected(token); setDirty(false); return; }
      // Deleted: fall back to another camera zone, or to an empty editor.
      const next = masks.find(m => m.token !== change.token);
      setSelected(next ? next.token : "");
      if (next) { setDraft(polygonToRect(next.polygon)); setType(next.type || options.types[0] || ""); setEnabled(next.enabled); }
      setDirty(false);
    },
  });
  const modeChange = useMutation({
    mutationFn: async () => { await onTurnOnZoneMode?.(); },
    onSuccess: () => { setConfirmingMode(false); refreshImage(); },
  });
  const busy = mutation.isPending || modeChange.isPending;

  const point = (e: React.PointerEvent): Point => { const bounds = svg.current!.getBoundingClientRect(); return { x: Math.max(0, Math.min(100, (e.clientX - bounds.left) / bounds.width * 100)), y: Math.max(0, Math.min(100, (e.clientY - bounds.top) / bounds.height * 100)) }; };
  const edit = (next: ZoneRect) => { setDraft(next); setDirty(true); };
  const onPointerDown = (e: React.PointerEvent) => {
    if (!allowed || busy) return;
    const target = (e.target as SVGElement).dataset;
    // Clicking a saved zone on the picture selects it.
    if (target.token) { choose(masks.find(m => m.token === target.token)); return; }
    const gesture = target.mode || "draw";
    // Drawing with nothing selected starts a new zone, if the camera has room for one.
    if (gesture === "draw" && !selected && full) return;
    drag.current = { start: point(e), rect: draft, mode: gesture, wasSelected: selected, wasDirty: dirty };
    svg.current?.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const gesture = drag.current;
    if (!gesture) return;
    const at = point(e), dx = at.x - gesture.start.x, dy = at.y - gesture.start.y;
    if (gesture.mode === "move") edit({ ...gesture.rect, x: Math.max(0, Math.min(100 - gesture.rect.width, gesture.rect.x + dx)), y: Math.max(0, Math.min(100 - gesture.rect.height, gesture.rect.y + dy)) });
    else if (gesture.mode === "resize") edit({ ...gesture.rect, width: Math.max(1, Math.min(100 - gesture.rect.x, gesture.rect.width + dx)), height: Math.max(1, Math.min(100 - gesture.rect.y, gesture.rect.height + dy)) });
    else if (Math.abs(dx) >= MIN_DRAG && Math.abs(dy) >= MIN_DRAG) {
      if (!selected) { mutation.reset(); setSelected(NEW); setType(options.types[0] || ""); setEnabled(true); }
      edit({ x: Math.min(at.x, gesture.start.x), y: Math.min(at.y, gesture.start.y), width: Math.abs(dx), height: Math.abs(dy) });
    } else if (gesture.wasSelected) { setDraft(gesture.rect); setDirty(gesture.wasDirty); }
  };
  const endDrag = (e: React.PointerEvent) => { drag.current = null; svg.current?.releasePointerCapture?.(e.pointerId); };

  const previewFill = person ? "fill-sky-400/15" : "fill-video-bg";
  const selectedIndex = masks.findIndex(m => m.token === selected);
  const selectedName = isNew ? "New zone" : selectedIndex >= 0 ? `Zone ${selectedIndex + 1}` : "";
  return <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="font-semibold">{person ? "Person detection zones preview" : preview ? "Privacy zones preview" : "Privacy zones"}</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {person ? "Mark an area where you would want person alerts. The current camera API supports turning person detection on or off for the whole frame." : preview ? "Mark an area to see how it would be hidden in the video." : "A privacy zone blacks out part of the picture, in live view and in recordings."}
        </p>
        {preview && <p className="mt-2 text-sm text-muted-foreground">Changes stay in this preview until you leave or reload.</p>}
      </div>
      {!preview && <Button variant="outline" size="sm" onClick={refreshImage}><RefreshCw className="size-4" />Refresh picture</Button>}
    </div>
    {!preview && mode && mode !== "Zone" && <div role="status" className="flex flex-wrap items-center justify-between gap-4 rounded-lg bg-warning-subtle p-4 text-sm">
      <p className="flex min-w-0 flex-1 items-start gap-2"><ShieldAlert className="mt-1 size-4 shrink-0 text-warning" />
        <span>{mode === "Full" ? "Privacy mode is Full, so the camera has stopped all video. Zones are only used in Zone mode." : masks.length ? "Your zones are saved, but they are not hiding anything yet. Privacy mode is None; zones only black out the video in Zone mode." : "Zones only black out the video when privacy mode is Zone. It is None right now."}</span>
      </p>
      {onTurnOnZoneMode && <Button variant="outline" size="sm" disabled={!allowed || busy} onClick={() => { modeChange.reset(); setConfirmingMode(true); }}>Turn on Zone mode</Button>}
    </div>}
    {!preview && mode === "Zone" && <p role="status" className="flex items-start gap-2 text-sm text-muted-foreground"><ShieldCheck className="mt-1 size-4 shrink-0 text-success" />Zone mode is on. Zones that are switched on are hidden in the video.</p>}
    <div className="relative aspect-video overflow-hidden rounded-xl bg-video-bg">
      {preview ? (
        <span className="pointer-events-none absolute left-2 top-2 z-10 rounded-md bg-video-bg px-2 py-1 text-xs text-video-fg">Sample frame</span>
      ) : serial && (
        <img src={`/api/v1/cameras/${encodeURIComponent(serial)}/snapshot?profile=medium&v=${imageVersion}`} alt="Camera reference for privacy zones" onError={() => setImageError(true)} className={imageError ? "hidden" : "absolute inset-0 size-full object-fill"} />
      )}
      {imageError && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-video-fg/70"><ImageOff className="size-8" /><p className="text-sm">Camera picture unavailable. You can still draw zones.</p></div>}
      <svg ref={svg} viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={person ? "Person detection zone editor" : "Privacy zone editor"} className={`absolute inset-0 size-full touch-none ${allowed && (selected || !full) ? "cursor-crosshair" : ""}`} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerCancel={endDrag}>
        {preview && <g className="pointer-events-none">
          <rect width="100" height="100" className="fill-slate-800" />
          <path d="M20 0V100 M40 0V100 M60 0V100 M80 0V100 M0 20H100 M0 40H100 M0 60H100 M0 80H100" fill="none" className="stroke-video-fg/20" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        </g>}
        {masks.filter(m => m.token !== selected && m.polygon.length).map(m => (
          <rect key={m.token} {...polygonToRect(m.polygon)} data-token={m.token} pointerEvents="all" vectorEffect="non-scaling-stroke" strokeWidth="2"
            className={`cursor-pointer ${preview ? "stroke-sky-400" : "stroke-video-fg"} ${m.enabled && preview ? previewFill : "fill-none"}`}
            strokeDasharray={m.enabled ? undefined : "5 4"} />
        ))}
        {selected && <>
          {/* Tinted only while there are unsaved changes, so a saved zone shows the camera's own mask underneath. */}
          <rect {...draft} data-mode="move" strokeWidth="2" vectorEffect="non-scaling-stroke" pointerEvents="all" strokeDasharray={enabled ? undefined : "5 4"}
            className={`cursor-move ${preview ? "stroke-sky-400" : "stroke-primary"} ${preview ? (enabled ? previewFill : "fill-none") : dirty ? "fill-primary/40" : "fill-none"}`} />
          <rect x={draft.x + draft.width - 2} y={draft.y + draft.height - 2} width="4" height="4" data-mode="resize"
            className={`cursor-se-resize ${preview ? "fill-sky-400" : "fill-primary"}`} />
        </>}
      </svg>
      {!selected && !masks.length && <p className="pointer-events-none absolute inset-x-0 bottom-4 mx-auto w-fit rounded-md bg-video-bg px-4 py-2 text-sm text-video-fg">Drag on the picture to draw your first zone</p>}
    </div>
    <div role="group" aria-label={`Selected ${zoneLabel}`} className="flex flex-wrap items-center gap-2">
      {masks.map((m, i) => <Button key={m.token} size="sm" variant={m.token === selected ? "default" : "outline"} aria-pressed={m.token === selected} disabled={busy} onClick={() => choose(m)}>Zone {i + 1}{m.enabled ? "" : " (off)"}</Button>)}
      {isNew && <Button size="sm" aria-pressed disabled={busy}>New zone (not saved)</Button>}
      <Button variant="outline" size="sm" disabled={!allowed || busy || full || isNew} onClick={() => choose()}><Plus className="size-4" />Add zone</Button>
      <span className="ml-auto text-xs text-muted-foreground">{masks.length} of {options.max_masks} {preview ? "preview zones" : "camera zones"} used</span>
    </div>
    {selected ? <>
      <p className="text-sm text-muted-foreground">{isNew ? "Drag on the picture to place the new zone, then save it." : `${selectedName} is selected. Drag it to move, drag its corner to resize, or draw a new rectangle for it.`}</p>
      <fieldset disabled={!allowed || busy} className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={enabled} onCheckedChange={checked => { setEnabled(checked === true); setDirty(true); }} />Zone enabled</label>
        {options.types.length > 1 && <label className="flex items-center gap-2 whitespace-nowrap text-sm">Mask type<NativeSelect value={type} onChange={e => { setType(e.target.value); setDirty(true); }}>{options.types.map(t => <option key={t}>{t}</option>)}</NativeSelect></label>}
      </fieldset>
      <details>
        <summary className="cursor-pointer text-sm text-primary-text">Set exact position</summary>
        <fieldset disabled={!allowed || busy} className="mt-4 grid gap-4 sm:grid-cols-4">{(["x", "y", "width", "height"] as const).map(key => <label className="vms-field" key={key}>{({ x: "Left", y: "Top", width: "Width", height: "Height" })[key]} (%)<Input type="number" aria-label={`Zone ${key}`} min={0} max={100} step="0.1" value={Number(draft[key].toFixed(1))} onChange={e => { const value = Math.max(0, Math.min(100, Number(e.target.value))); edit({ ...draft, [key]: key === "width" ? Math.min(value, 100 - draft.x) : key === "height" ? Math.min(value, 100 - draft.y) : key === "x" ? Math.min(value, 100 - draft.width) : Math.min(value, 100 - draft.height) }); }} /></label>)}</fieldset>
      </details>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {dirty && !isNew && <span className="mr-auto text-sm text-warning">Unsaved changes to {selectedName}</span>}
        {isNew
          ? <Button variant="outline" disabled={busy} onClick={() => { const back = masks[0]; if (back) choose(back); else { setSelected(""); setDirty(false); } }}>Discard new zone</Button>
          : <Button variant="outline" disabled={!allowed || busy} onClick={() => { if (preview) mutation.mutate({ token: selected }); else setDeleting(true); }}><Trash2 className="size-4" />Delete zone</Button>}
        <Button disabled={!allowed || !dirty || draft.width <= 0 || draft.height <= 0 || busy || isNew && full}
          onClick={() => mutation.mutate({ token: isNew ? "" : selected, draft: { polygon: rectToPolygon(draft), type, enabled } })}>
          <Save className="size-4" />{preview ? "Save preview zone" : "Save zone to camera"}
        </Button>
      </div>
    </> : masks.length > 0 && <p className="text-sm text-muted-foreground">Pick a zone to change it, or add a new one.</p>}
    {mutation.error && <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-sm text-critical">{mutation.error.message}</p>}
    {modeChange.error && !confirmingMode && <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-sm text-critical">{modeChange.error.message}</p>}
    {mutation.isSuccess && !dirty && <p role="status" className="text-sm text-success">{preview ? "Preview updated." : mutation.variables?.draft ? "Saved to the camera." : "Zone deleted from the camera."}</p>}
    {!preview && <Dialog open={deleting} onOpenChange={setDeleting}><DialogContent><DialogHeader><DialogTitle>Delete {selectedName.toLowerCase()}?</DialogTitle><DialogDescription>This area of {cameraName} will be visible again in live view and in new recordings.</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" disabled={busy} onClick={() => setDeleting(false)}>Keep zone</Button><Button variant="destructive" disabled={busy} onClick={() => mutation.mutate({ token: selected })}>Delete zone from camera</Button></DialogFooter></DialogContent></Dialog>}
    {!preview && <Dialog open={confirmingMode} onOpenChange={setConfirmingMode}><DialogContent><DialogHeader><DialogTitle>Turn on Zone mode?</DialogTitle><DialogDescription>{cameraName} will black out every zone that is switched on, in live view and in new recordings. Footage of those areas cannot be recovered later.</DialogDescription></DialogHeader>{modeChange.error && <p role="alert" className="rounded-lg bg-critical-subtle p-4 text-sm text-critical">{modeChange.error.message}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setConfirmingMode(false)}>Leave mode unchanged</Button><Button disabled={busy} onClick={() => modeChange.mutate()}>Turn on Zone mode</Button></DialogFooter></DialogContent></Dialog>}
  </section>;
}
