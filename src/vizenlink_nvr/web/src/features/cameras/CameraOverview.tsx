import { NativeSelect } from "@/components/ui/native-select";
import { useState } from "react";
import { Link } from "react-router";
import { Cctv, Plus, Search, LayoutGrid, List, MapPin, Play, Settings, History, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageIntro } from "@/components/PageIntro";
import { isCameraOffline } from "@/lib/recorder-status";
import type { CameraInfo, RecordingStatusItem } from "@/lib/queries";

export function CameraOverview({ cameras, recordings }: { cameras: CameraInfo[]; recordings: RecordingStatusItem[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [location, setLocation] = useState("");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const online = cameras.filter(c => !isCameraOffline(c)).length;
  const recording = new Set(recordings.filter(r => r.is_recording === true).map(r => r.camera_serial));
  const locations = [...new Set(cameras.map(c => c.location).filter(Boolean))].sort();
  const filtered = cameras.filter(c => `${c.name} ${c.location || ""} ${c.serial}`.toLowerCase().includes(query.toLowerCase()) &&
    (!status || (status === "online" ? !isCameraOffline(c) : status === "offline" ? isCameraOffline(c) : recording.has(c.serial))) &&
    (!location || c.location === location));
  const clear = () => { setQuery(""); setStatus(""); setLocation(""); };
  return <div className="flex flex-col gap-6">
    <PageIntro description="Check connections, open a live feed, or fine-tune a camera."
      actions={<><Button variant="outline" asChild><Link to="/live"><LayoutGrid className="size-4" />Open multiview</Link></Button><Button asChild><Link to="/cameras/add"><Plus className="size-4" />Add camera</Link></Button></>} />
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card px-4 py-4 text-sm">
      <span className="flex items-center gap-2"><Cctv className="size-4 text-primary" /><strong>{cameras.length}</strong> cameras</span>
      <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-success" /><strong>{online}</strong> reachable</span>
      <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-rec" /><strong>{recording.size}</strong> recording</span>
      <span className="text-muted-foreground">{cameras.length - online} need attention</span>
    </div>
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-48 flex-1"><Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search cameras" placeholder="Search by name, location or serial…" value={query} onChange={e => setQuery(e.target.value)} className="pl-12" /></div>
      <NativeSelect aria-label="Filter camera status" className="w-auto" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option><option value="online">Reachable</option><option value="offline">Needs attention</option><option value="recording">Recording</option></NativeSelect>
      <NativeSelect aria-label="Filter camera location" className="w-auto" value={location} onChange={e => setLocation(e.target.value)}><option value="">All locations</option>{locations.map(l => <option key={l}>{l}</option>)}</NativeSelect>
      <div className="flex gap-1 rounded-lg border border-border bg-card p-1"><Button size="icon" variant={layout === "grid" ? "secondary" : "ghost"} aria-label="Camera grid" aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}><LayoutGrid className="size-4" /></Button><Button size="icon" variant={layout === "list" ? "secondary" : "ghost"} aria-label="Camera list" aria-pressed={layout === "list"} onClick={() => setLayout("list")}><List className="size-4" /></Button></div>
    </div>
    <div className={layout === "grid" ? "grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" : "flex flex-col gap-2"}>
      {filtered.map((cam, index) => <article key={cam.serial} className={"camera-overview-card group overflow-hidden rounded-xl border border-border bg-card " + (layout === "list" ? "flex flex-wrap items-center gap-4 p-4" : "")}>
        {layout === "grid" && <Link to={`/live?camera=${encodeURIComponent(cam.serial)}`} aria-label={`Watch ${cam.name}`} className="camera-poster relative flex aspect-video items-center justify-center overflow-hidden">
          <div className="camera-poster-ring"><Cctv className="size-8" /></div>
          {!isCameraOffline(cam) && (
            <img
              src={`/api/v1/cameras/${encodeURIComponent(cam.serial)}/snapshot?profile=low`}
              alt=""
              loading="lazy"
              className="absolute inset-0 z-10 size-full bg-video-bg object-cover transition-transform duration-300 group-hover:scale-[1.02]"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          )}
          <span className="absolute left-2 top-2 z-20 rounded border border-white/15 bg-black/50 px-2 py-1 text-xs text-white/90">CH {String(index + 1).padStart(2, "0")}</span>
          <span className="absolute right-2 top-2 z-20 rounded border border-white/15 bg-black/50 px-2 py-1 font-mono text-xs text-white/90">{cam.serial}</span>
          <span className="absolute bottom-2 left-2 z-20 rounded bg-black/50 px-2 py-1 text-xs text-white/90">{isCameraOffline(cam) ? "Camera unavailable" : "Open live feed"}</span>
          <span className="absolute bottom-2 right-2 z-20 flex size-8 items-center justify-center rounded-full bg-black/50 text-white"><Play className="size-4" /></span>
        </Link>}
        <div className={layout === "grid" ? "flex flex-col gap-4 p-4" : "flex min-w-0 flex-1 flex-wrap items-center gap-4"}>
          <div className={layout === "list" ? "min-w-48 flex-1" : "min-w-0 flex-1"}><h2 className="truncate font-semibold">{cam.name}</h2><p className="mt-1 flex items-center gap-1 truncate text-xs text-muted-foreground"><MapPin className="size-4 shrink-0" /><span className="truncate">{cam.location || "No location set"}</span> · <span className="font-mono">{cam.serial}</span></p></div>
          <div className="flex flex-wrap gap-2 text-xs"><span className={"status-pill " + (isCameraOffline(cam) ? "bg-offline-subtle text-offline" : "bg-success-subtle text-success")}>{isCameraOffline(cam) ? "Needs attention" : "Reachable"}</span><span className={"status-pill " + (recording.has(cam.serial) ? "bg-critical-subtle text-rec" : "bg-muted text-muted-foreground")}>{recording.has(cam.serial) ? "Recording" : recordings.find(r => r.camera_serial === cam.serial)?.mode === "off" ? "Recording off" : "Not confirmed recording"}</span></div>
          <div className={layout === "grid" ? "flex items-center gap-1 border-t border-border pt-2" : "flex items-center gap-1 ml-auto"}>
            <Button size="sm" variant="ghost" asChild><Link to={`/live?camera=${encodeURIComponent(cam.serial)}`}><Play className="size-4" />Live</Link></Button>
            <Button size="sm" variant="ghost" asChild><Link to={`/playback?camera=${encodeURIComponent(cam.serial)}`}><History className="size-4" />Playback</Link></Button>
            <Button size="sm" variant="ghost" asChild><Link to={`/cameras/${encodeURIComponent(cam.serial)}`}><Settings className="size-4" />Settings<ArrowUpRight className="size-4" /></Link></Button>
          </div>
        </div>
      </article>)}
    </div>
    {filtered.length === 0 && <div className="rounded-xl border border-dashed border-border bg-card p-12 text-center"><Search className="mx-auto mb-4 size-8 text-muted-foreground" /><h3 className="font-semibold">No cameras match these filters</h3><Button className="mt-4" variant="outline" onClick={clear}>Show all cameras</Button></div>}
  </div>;
}
