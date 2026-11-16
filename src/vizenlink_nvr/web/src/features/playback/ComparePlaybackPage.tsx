import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowLeft, Film, LayoutGrid, Loader2, Pause, Play, RotateCcw, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { PageIntro } from "@/components/PageIntro";
import { InlineError } from "@/components/InlineError";
import { useCameras } from "@/lib/queries";
import { formatTime, useSiteTimeZone, zonedDayBounds } from "@/lib/time";
import { toIsoDate, type TimelineSegment } from "@/lib/timeline";
import { useTimeline } from "./api";
import { parseTimeToDate } from "./usePlaybackEngine";

export function coveringSegment(segments: TimelineSegment[], instant: number) {
  return segments.find(s => new Date(s.start_time).getTime() <= instant && instant < new Date(s.end_time).getTime());
}

function CompareTile({ serial, name, day, zone, instant, playing, rate, onSeek }: { serial: string; name: string; day: string; zone: string; instant: number; playing: boolean; rate: number; onSeek: (time: number) => void }) {
  const timeline = useTimeline(serial, day, zone);
  const video = useRef<HTMLVideoElement>(null);
  const current = useRef({ instant, playing, rate });
  current.current = { instant, playing, rate };
  const [error, setError] = useState(false);
  const segment = coveringSegment(timeline.data?.segments || [], instant);
  const sync = () => {
    const el = video.current;
    if (!el || !segment) return;
    const offset = Math.max(0, (current.current.instant - new Date(segment.start_time).getTime()) / 1000);
    if (el.readyState >= 1 && Math.abs(el.currentTime - offset) > 0.3) el.currentTime = offset;
    el.playbackRate = current.current.rate;
    if (current.current.playing) { if (el.paused) void el.play()?.catch(() => setError(true)); }
    else el.pause();
  };
  useEffect(() => { sync(); }, [instant, playing, rate, segment?.id]);
  useEffect(() => setError(false), [segment?.id]);
  return <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card" aria-label={`${name} comparison`}>
    <div className="relative flex min-h-0 flex-1 items-center justify-center bg-video-bg text-video-fg">
      <video ref={video} src={segment ? `/api/v1/playback/segment/${segment.id}` : undefined} playsInline muted onLoadedMetadata={sync} onCanPlay={sync} onError={() => setError(true)} className="size-full object-contain" />
      <span className="absolute left-2 top-2 flex items-center gap-2 rounded bg-video-overlay/85 px-2 py-1 text-xs font-semibold">
        <span>{name}</span>
        {segment && <span className="rounded bg-primary/80 px-1 text-xs font-semibold uppercase tracking-wide text-primary-foreground">Synced</span>}
      </span>
      {timeline.isPending ? <Loader2 className="absolute size-6 animate-spin" /> : !segment || error || timeline.error ? <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-video-bg p-4 text-center"><Film className="size-6 text-video-fg/60" /><p className="text-sm">{timeline.error ? "Couldn't load the timeline" : error ? "Couldn't play this recording" : "No footage at this time"}</p>{(timeline.error || error) && <Button variant="outline" size="sm" className="bg-video-overlay text-video-fg" onClick={() => { setError(false); void timeline.refetch(); video.current?.load(); }}>Reload recording</Button>}</div> : null}
    </div>
    <div className="flex items-center justify-between gap-2 px-4 py-2 text-xs text-muted-foreground"><span>{timeline.data?.segments.length ?? 0} recorded segments</span><Link className="text-primary-text hover:underline" to={`/playback?${new URLSearchParams({ camera: serial, t: new Date(instant).toISOString() })}`}>Open single camera</Link></div>
  </section>;
}

function CameraTimeline({ serial, name, day, zone, instant, onSeek }: {
  serial: string; name: string; day: string; zone: string; instant: number; onSeek: (time: number) => void;
}) {
  const timeline = useTimeline(serial, day, zone);
  const [start, end] = zonedDayBounds(day, zone);
  const duration = end.getTime() - start.getTime();
  return (
    <div className="grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[10rem_minmax(0,1fr)]">
      <span className="truncate text-xs" title={name}>{name}</span>
      <div className="relative h-8 overflow-hidden rounded bg-muted" role="group" aria-label={`${name} recorded times`}>
        {timeline.data?.segments.map(segment => {
          const first = Math.max(start.getTime(), new Date(segment.start_time).getTime());
          const last = Math.min(end.getTime(), new Date(segment.end_time).getTime());
          if (last <= first) return null;
          return <button key={segment.id} type="button"
            aria-label={`Seek all cameras to ${name} at ${formatTime(new Date(first), zone)}`}
            className="absolute inset-y-1 min-w-px rounded bg-primary/70 hover:bg-primary focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => onSeek(first)}
            // dynamic-style: recording spans clipped to the selected site day.
            style={{ left: `${(first - start.getTime()) / duration * 100}%`, width: `${(last - first) / duration * 100}%` }} />;
        })}
        {timeline.isPending && <span className="absolute inset-0 flex items-center justify-center text-xs">Loading…</span>}
        {timeline.error && <button type="button" className="absolute inset-0 text-xs text-critical" onClick={() => void timeline.refetch()}>Reload timeline</button>}
        <span className="pointer-events-none absolute inset-y-0 w-0.5 bg-foreground"
          // dynamic-style: every row uses the same playback instant.
          style={{ left: `${Math.max(0, Math.min(100, (instant - start.getTime()) / duration * 100))}%` }} />
      </div>
    </div>
  );
}

export function ComparePlaybackPage() {
  const [params, setParams] = useSearchParams();
  const zone = useSiteTimeZone();
  const cameras = useCameras(true);
  const initial = new Date(params.get("t") || new Date());
  const [instant, setInstant] = useState(Number.isNaN(initial.getTime()) ? Date.now() : initial.getTime());
  const day = toIsoDate(new Date(instant), zone);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [chooseOpen, setChooseOpen] = useState(false);
  const [timeInput, setTimeInput] = useState("");
  const [timeError, setTimeError] = useState("");
  const selected = useMemo(() => {
    const ids = params.getAll("camera");
    return (cameras.data || []).filter(c => ids.includes(c.serial));
  }, [params, cameras.data]);
  const [start, end] = zonedDayBounds(day, zone);
  const latest = useRef({ instant, rate, end: end.getTime() });
  latest.current = { instant, rate, end: end.getTime() };
  useEffect(() => {
    if (!playing) return;
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const next = latest.current.instant + (now - previous) * latest.current.rate;
      previous = now;
      latest.current.instant = Math.min(next, latest.current.end - 1);
      if (next >= latest.current.end) { setInstant(latest.current.end - 1); setPlaying(false); }
      else setInstant(next);
    }, 250);
    return () => window.clearInterval(timer);
  }, [playing]);
  const seek = (time: number) => {
    latest.current.instant = time;
    setInstant(time);
    setParams(prev => { const next = new URLSearchParams(prev); next.set("t", new Date(time).toISOString()); return next; }, { replace: true });
  };
  const toggle = (serial: string) => setParams(prev => {
    const next = new URLSearchParams(prev);
    const ids = new Set(prev.getAll("camera"));
    if (ids.has(serial)) ids.delete(serial);
    else ids.add(serial);
    next.delete("camera");
    ids.forEach(id => next.append("camera", id));
    return next;
  });
  const selectAll = (include: boolean) => setParams(previous => {
    const next = new URLSearchParams(previous);
    next.delete("camera");
    if (include) cameras.data?.forEach(camera => next.append("camera", camera.serial));
    return next;
  });
  const loadPresetGrid = () => setParams(previous => {
    const next = new URLSearchParams(previous);
    next.delete("camera");
    const onlineFirst = [
      ...(cameras.data || []).filter(c => c.is_online !== false),
      ...(cameras.data || []).filter(c => c.is_online === false),
    ].slice(0, 4);
    onlineFirst.forEach(camera => next.append("camera", camera.serial));
    return next;
  });
  return <div
    className="flex flex-col gap-2 p-2 overflow-hidden"
    // dynamic-style: fit comparison view to viewport height when cameras are selected so tiles and timeline stay on one screen
    style={selected.length ? { height: "calc(100dvh - 5rem)" } : undefined}
  >
    <PageIntro description="Review multiple cameras together on a synchronized clock and shared timeline."
      actions={<><Button variant="outline" asChild><Link to={`/playback?${new URLSearchParams({ camera: selected[0]?.serial || "", t: new Date(instant).toISOString(), mode: "sync" })}`}><ArrowLeft className="size-4" />Unified playback</Link></Button><Button variant="outline" asChild><Link to={`/playback?${new URLSearchParams({ camera: selected[0]?.serial || "", t: new Date(instant).toISOString() })}`}>Single camera</Link></Button><Button onClick={() => setChooseOpen(true)}><LayoutGrid className="size-4" />Choose cameras</Button></>} />
    {cameras.error && <InlineError message={cameras.error.message} actionLabel="Reload cameras" onAction={() => void cameras.refetch()} />}
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm">Date<Input aria-label="Comparison date" type="date" value={day} onChange={e => { if (e.target.value) { setPlaying(false); seek(zonedDayBounds(e.target.value, zone)[0].getTime()); } }} /></label>
        <form className="flex items-center gap-2" onSubmit={e => { e.preventDefault(); const target = parseTimeToDate(day, timeInput, zone); if (target) { setTimeError(""); seek(target.getTime()); } else setTimeError("Enter a time such as 14:30."); }}><Input className="w-32" aria-label="Comparison jump time" placeholder="HH:MM:SS" value={timeInput} onChange={e => setTimeInput(e.target.value)} /><Button variant="outline" type="submit">Jump to time</Button></form>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          {cameras.data && cameras.data.length > 0 && selected.length < Math.min(4, cameras.data.length) && (
            <Button variant="outline" size="sm" onClick={loadPresetGrid}>Fill 2×2 grid</Button>
          )}
          <span>{zone} · {selected.length} cameras selected</span>
        </div>
        {timeError && <p role="alert" className="w-full text-xs text-critical">{timeError}</p>}
      </div>
      {cameras.data && cameras.data.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2">
          <span className="text-xs font-semibold text-muted-foreground">Channels:</span>
          {cameras.data.slice(0, 6).map(cam => {
            const active = selected.some(s => s.serial === cam.serial);
            return (
              <Button
                key={cam.serial}
                type="button"
                size="sm"
                variant={active ? "secondary" : "outline"}
                className="h-8 gap-2 px-2 text-xs"
                onClick={() => toggle(cam.serial)}
              >
                <span className={`size-2 rounded-full ${cam.is_online !== false ? "bg-success" : "bg-muted-foreground"}`} />
                <span>{cam.name}</span>
              </Button>
            );
          })}
        </div>
      )}
    </div>
    {selected.length ? <><div className={`grid min-h-0 flex-1 gap-2 ${selected.length <= 4 ? "md:grid-cols-2" : "md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"}`}>{selected.map(c => <CompareTile key={c.serial} serial={c.serial} name={c.name} day={day} zone={zone} instant={instant} playing={playing} rate={rate} onSeek={seek} />)}</div><div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-2"><div className="flex flex-wrap items-center justify-between gap-4"><div className="flex items-center gap-2"><Button variant="outline" size="icon" aria-label="Back 10 seconds on all cameras" onClick={() => seek(Math.max(start.getTime(), instant - 10000))}><RotateCcw className="size-4" /></Button><Button size="icon" aria-label={playing ? "Pause all cameras" : "Play all cameras"} onClick={() => setPlaying(!playing)}>{playing ? <Pause className="size-4" /> : <Play className="size-4" />}</Button><Button variant="outline" size="icon" aria-label="Forward 10 seconds on all cameras" onClick={() => seek(Math.min(end.getTime() - 1, instant + 10000))}><RotateCw className="size-4" /></Button><span className="ml-2 font-semibold tabular-nums">{formatTime(new Date(instant), zone)}</span></div><label className="flex items-center gap-2 text-sm">Speed<NativeSelect aria-label="Comparison playback speed" size="sm" className="w-auto" value={rate} onChange={e => setRate(Number(e.target.value))}>{[0.5, 1, 2, 4].map(v => <option key={v} value={v}>{v}×</option>)}</NativeSelect></label></div><div className="flex flex-col gap-2" aria-label="Synchronized camera timelines">
      {selected.map(camera => <CameraTimeline key={camera.serial} serial={camera.serial} name={camera.name}
        day={day} zone={zone} instant={instant} onSeek={seek} />)}
    </div><input type="range" className="w-full accent-primary" aria-label="Shared playback position" min={start.getTime()} max={end.getTime() - 1} step={1000} value={instant} onChange={e => seek(Number(e.target.value))} /><p className="text-xs text-muted-foreground">All views follow the same recorder timestamp. Use single-camera playback to export a clip or capture a snapshot.</p></div></> : <div className="flex min-h-80 flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border bg-card p-8 text-center"><LayoutGrid className="size-12 text-primary" /><h3 className="text-xl font-semibold">Choose your angles</h3><p className="text-sm text-muted-foreground">Select up to 4 or more cameras to scrub and play together on one shared clock.</p><div className="flex flex-wrap items-center justify-center gap-2"><Button onClick={() => setChooseOpen(true)}>Select cameras to compare</Button>{(cameras.data?.length ?? 0) > 0 && <Button variant="outline" onClick={loadPresetGrid}>Load 2×2 online cameras</Button>}</div></div>}
    <Dialog open={chooseOpen} onOpenChange={setChooseOpen}><DialogContent><DialogHeader><DialogTitle>Choose cameras to compare</DialogTitle><DialogDescription>Choose any of your accessible cameras. Every selected view follows the same timestamp.</DialogDescription></DialogHeader><div className="flex flex-wrap gap-2">
      <Button variant="outline" disabled={!cameras.data?.length} onClick={() => selectAll(true)}>Select all cameras</Button>
      <Button variant="outline" disabled={!selected.length} onClick={() => selectAll(false)}>Clear selection</Button>
    </div><div className="flex max-h-80 flex-col gap-2 overflow-y-auto">{cameras.data?.map(c => <label key={c.serial} className="flex cursor-pointer items-center gap-4 rounded-lg border border-border p-4"><Checkbox checked={selected.some(s => s.serial === c.serial)} onCheckedChange={() => toggle(c.serial)} /><span className="flex-1 text-sm">{c.name}<span className="block text-xs text-muted-foreground">{c.location || c.serial}</span></span></label>)}</div><Button onClick={() => setChooseOpen(false)}>View selected cameras</Button></DialogContent></Dialog>
  </div>;
}
