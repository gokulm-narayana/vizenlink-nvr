import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Cctv, Plus, Search, Star, History, Settings, X, Save, Trash2 } from "lucide-react";
import { useCameras, useRecordingStatus, useCurrentUser } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { GridStorage, type GridDimension } from "@/services/grid_storage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineError } from "@/components/InlineError";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { cn } from "cn";
import { LiveToolbar } from "./LiveToolbar";
import { VideoTile } from "./VideoTile";
import { LIVE_COPY } from "./copy";

type SavedView = { name: string; serials: string[]; dimension: GridDimension };
type Preferences = { favorites: string[]; views: SavedView[] };
function readPreferences(key: string): Preferences {
  try {
    const data = JSON.parse(localStorage.getItem(key) || "{}");
    return {
      favorites: Array.isArray(data.favorites) ? data.favorites.filter((v: unknown) => typeof v === "string") : [],
      views: Array.isArray(data.views) ? data.views.filter((v: SavedView) => typeof v?.name === "string" && Array.isArray(v.serials) && v.serials.every(s => typeof s === "string") && [1,2,3,4].includes(v.dimension)) : [],
    };
  } catch { return { favorites: [], views: [] }; }
}

export const LivePage: React.FC = () => {
  const { data: cameras = [], isLoading, error, refetch } = useCameras();
  const { data: recList = [] } = useRecordingStatus();
  const user = useCurrentUser();
  const viewMode = useUiStore(s => s.viewMode);
  const storageKey = `vizenlink_live_preferences_${user?.id ?? "guest"}`;
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey));
  useEffect(() => { setPreferences(readPreferences(storageKey)); }, [storageKey]);
  const [dimension, setDimension] = useState<GridDimension>(() => GridStorage.load().dimension);
  const [page, setPage] = useState(() => GridStorage.load().page);
  useEffect(() => {
    if (cameras.length === 1 && !localStorage.getItem("vizenlink_nvr_grid_layout_v1")) setDimension(1);
  }, [cameras.length]);
  const [maximizedSerial, setMaximizedSerial] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [selectedView, setSelectedView] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [viewName, setViewName] = useState("");
  const [selection, setSelection] = useState<string[] | null>(null);
  const [chooseOpen, setChooseOpen] = useState(false);
  useEffect(() => { setMaximizedSerial(null); }, [search, group, favoritesOnly, selection]);
  const [draftSelection, setDraftSelection] = useState<string[]>([]);
  const isManager = user?.role === "operator" || user?.role === "owner";

  const persist = (next: Preferences) => {
    setPreferences(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); }
    catch { toast.error("Your browser couldn't save this preference. It will last for this visit only."); }
  };
  const groups = [...new Set(cameras.map(c => c.group_tag || c.location).filter(Boolean))].sort();
  const filtered = cameras.filter(c =>
    (!selection || selection.includes(c.serial)) &&
    (!group || (c.group_tag || c.location) === group) &&
    (!favoritesOnly || preferences.favorites.includes(c.serial)) &&
    `${c.name} ${c.location || ""} ${c.group_tag || ""} ${c.serial}`.toLowerCase().includes(search.toLowerCase())
  );
  // The policy endpoint does not guarantee active recording. Only display REC when confirmed.
  const recordingSerials = useMemo(() => new Set(recList.filter(r => r.is_recording === true).map(r => r.camera_serial)), [recList]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / (dimension * dimension)));
  const currentPage = Math.min(page, totalPages - 1);
  const visible = filtered.slice(currentPage * dimension * dimension, (currentPage + 1) * dimension * dimension);
  const expanded = cameras.find(c => c.serial === maximizedSerial);
  const resetFilters = () => { setSearch(""); setGroup(""); setFavoritesOnly(false); setSelectedView(""); setSelection(null); setPage(0); };
  const changeLayout = (dim: GridDimension) => { setDimension(dim); setPage(0); GridStorage.save({ dimension: dim, page: 0, slotAssignments: {} }); };
  const selectView = (name: string) => {
    resetFilters(); setSelectedView(name);
    const view = preferences.views.find(v => v.name === name);
    if (view) { setSelection(view.serials); changeLayout(view.dimension); }
  };
  const saveView = () => {
    const name = viewName.trim();
    if (!name || !filtered.length) return;
    if (preferences.views.some(v => v.name.toLowerCase() === name.toLowerCase())) { toast.error("Choose a different name. A view with that name already exists."); return; }
    persist({ ...preferences, views: [...preferences.views, { name, serials: filtered.map(c => c.serial), dimension }] });
    setSelection(filtered.map(c => c.serial)); setSelectedView(name); setSaveOpen(false); setViewName(""); toast.success("View saved on this browser");
  };

  if (isLoading) return <div className="grid gap-4 p-4 sm:grid-cols-2" aria-label="Loading cameras">{[1,2,3,4].map(i => <Skeleton key={i} className="aspect-video" />)}</div>;
  if (error) return <InlineError message="Couldn't load your cameras." actionLabel="Reload cameras" onAction={() => void refetch()} />;
  if (!cameras.length) return <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
    <div className="rounded-xl bg-selected p-6 text-primary"><Cctv className="size-10" /></div>
    <h2 className="text-xl font-semibold">{isManager ? LIVE_COPY.EMPTY_HEADING_OPERATOR : LIVE_COPY.EMPTY_HEADING_VIEWER}</h2>
    <p className="max-w-md text-muted-foreground">{isManager ? LIVE_COPY.EMPTY_BODY_OPERATOR : LIVE_COPY.EMPTY_BODY_VIEWER}</p>
    {isManager && <Button asChild><Link to="/cameras/add"><Plus className="size-4" />Add camera</Link></Button>}
  </div>;

  return <div className="flex min-w-0 flex-col gap-4">
    <div className="flex flex-wrap items-center justify-between gap-4 px-2 pt-2">
      <div><h2 className="text-xl font-semibold">Your cameras</h2><p className="text-sm text-muted-foreground">Watch live, revisit a moment, or create your own camera view.</p></div>
      {isManager && <Button asChild><Link to="/cameras/add"><Plus className="size-4" />Add camera</Link></Button>}
    </div>
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card p-4">
      <div className="relative min-w-0 flex-1 basis-52"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input aria-label="Search cameras" placeholder="Search cameras or locations…" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }} className="pl-8" /></div>
      <select aria-label="Camera group" className="vms-select" value={group} onChange={e => { setGroup(e.target.value); setPage(0); }}><option value="">All locations</option>{groups.map(g => <option key={g} value={g}>{g}</option>)}</select>
      <Button variant={favoritesOnly ? "secondary" : "outline"} aria-pressed={favoritesOnly} onClick={() => { setFavoritesOnly(!favoritesOnly); setPage(0); }}><Star className="size-4" />Favorites</Button>
      <Button variant="outline" onClick={() => { setDraftSelection(selection || cameras.map(c => c.serial)); setChooseOpen(true); }}>Choose cameras</Button>
      {(search || group || favoritesOnly || selection) && <Button variant="ghost" onClick={resetFilters}>Show all</Button>}
    </div>
    <div className="flex flex-wrap items-center gap-4 px-2">
      <label htmlFor="saved-view" className="text-sm font-semibold">Saved views</label>
      <select id="saved-view" className="vms-select" value={selectedView} onChange={e => selectView(e.target.value)}><option value="">All cameras</option>{preferences.views.map(v => <option key={v.name} value={v.name}>{v.name}</option>)}</select>
      <Button variant="ghost" disabled={!filtered.length} onClick={() => setSaveOpen(true)}><Save className="size-4" />Save current view</Button>
      {selectedView && <Button variant="ghost" aria-label={`Delete saved view ${selectedView}`} onClick={() => { persist({ ...preferences, views: preferences.views.filter(v => v.name !== selectedView) }); resetFilters(); }}><Trash2 className="size-4" /></Button>}
    </div>
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <LiveToolbar dimension={dimension} onDimensionChange={changeLayout} currentPage={currentPage} totalPages={totalPages} onPageChange={p => { setPage(p); GridStorage.save({ dimension, page: p, slotAssignments: {} }); }} totalCameras={filtered.length} viewMode={viewMode} />
      {filtered.length === 0 ? <div className="flex flex-col items-center gap-4 p-12 text-center"><Search className="size-8 text-muted-foreground" /><h3 className="font-semibold">No cameras in this view</h3><p className="text-muted-foreground">Try another search, or add cameras to your favorites.</p><Button variant="outline" onClick={resetFilters}>Show all cameras</Button></div> :
      <div className={cn("grid gap-4 p-4", expanded ? "grid-cols-1" : dimension === 1 ? "grid-cols-1" : dimension === 2 ? "grid-cols-1 sm:grid-cols-2" : dimension === 3 ? "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3" : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-4")}>
        {(expanded ? [expanded] : visible).map(cam => <div key={cam.serial} className="min-w-0 overflow-hidden rounded-lg border border-border">
          <VideoTile serial={cam.serial} name={cam.name} isRecording={recordingSerials.has(cam.serial)} isMaximized={!!expanded} lastSeenAt={cam.last_seen_at} viewMode={viewMode} onToggleMaximize={() => setMaximizedSerial(expanded ? null : cam.serial)} />
          <div className="flex flex-wrap items-center gap-1 bg-card px-2 py-2">
            <Button variant="ghost" size="icon" aria-label={`${preferences.favorites.includes(cam.serial) ? "Remove" : "Add"} ${cam.name} ${preferences.favorites.includes(cam.serial) ? "from" : "to"} favorites`} aria-pressed={preferences.favorites.includes(cam.serial)} onClick={() => persist({ ...preferences, favorites: preferences.favorites.includes(cam.serial) ? preferences.favorites.filter(s => s !== cam.serial) : [...preferences.favorites, cam.serial] })}><Star className={cn("size-4", preferences.favorites.includes(cam.serial) && "fill-primary text-primary")} /></Button>
            <Button variant="ghost" size="sm" asChild><Link to={`/playback?camera=${encodeURIComponent(cam.serial)}`}><History className="size-4" />Playback</Link></Button>
            <Button variant="ghost" size="sm" asChild><Link to={`/playback?camera=${encodeURIComponent(cam.serial)}&t=${encodeURIComponent(new Date(Date.now() - 300000).toISOString())}`}>Last 5 min</Link></Button>
            {isManager && <Button variant="ghost" size="icon" aria-label={`Settings for ${cam.name}`} asChild><Link aria-label={`Settings for ${cam.name}`} to={`/cameras/${encodeURIComponent(cam.serial)}`}><Settings className="size-4" /></Link></Button>}
            {expanded && <Button variant="outline" size="sm" onClick={() => setMaximizedSerial(null)}><X className="size-4" />Back to grid</Button>}
          </div>
        </div>)}
      </div>}
    </div>
    <Dialog open={saveOpen} onOpenChange={setSaveOpen}><DialogContent><DialogHeader><DialogTitle>Save this camera view</DialogTitle><DialogDescription>Save the {filtered.length} selected cameras and grid layout on this browser.</DialogDescription></DialogHeader><label className="vms-field">View name<Input autoFocus maxLength={60} placeholder="e.g. Entrances" value={viewName} onChange={e => setViewName(e.target.value)} onKeyDown={e => { if (e.key === "Enter") saveView(); }} /></label><DialogFooter><Button variant="outline" onClick={() => setSaveOpen(false)}>Don&apos;t save</Button><Button disabled={!viewName.trim()} onClick={saveView}>Save view</Button></DialogFooter></DialogContent></Dialog>
    <Dialog open={chooseOpen} onOpenChange={setChooseOpen}><DialogContent><DialogHeader><DialogTitle>Choose cameras</DialogTitle><DialogDescription>Select the cameras you want to watch together.</DialogDescription></DialogHeader><div className="flex gap-2"><Button variant="outline" onClick={() => setDraftSelection(cameras.map(c => c.serial))}>Select all</Button><Button variant="ghost" onClick={() => setDraftSelection([])}>Clear selection</Button></div><div className="max-h-80 overflow-y-auto">{cameras.map(c => <label key={c.serial} className="flex cursor-pointer items-center gap-4 border-b border-border py-4"><input type="checkbox" checked={draftSelection.includes(c.serial)} onChange={e => setDraftSelection(e.target.checked ? [...draftSelection, c.serial] : draftSelection.filter(s => s !== c.serial))} /><span>{c.name}<span className="block text-xs text-muted-foreground">{c.location || c.serial}</span></span></label>)}</div><DialogFooter><Button variant="outline" onClick={() => setChooseOpen(false)}>Keep current cameras</Button><Button disabled={!draftSelection.length} onClick={() => { resetFilters(); setSelection(draftSelection); setChooseOpen(false); }}>Show {draftSelection.length} cameras</Button></DialogFooter></DialogContent></Dialog>
  </div>;
};
export default LivePage;
