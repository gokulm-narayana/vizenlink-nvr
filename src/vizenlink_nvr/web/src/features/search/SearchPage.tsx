import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Search, SlidersHorizontal, UserRound, Car, Footprints, Film, Image, CalendarDays, ArrowUpRight, Bookmark, X, LayoutGrid, List, Lock, Play, Clock, ScanSearch } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { PageIntro } from "@/components/PageIntro";
import { InlineError } from "@/components/InlineError";
import { apiFetch } from "@/lib/api";
import { useCameras, useCurrentUser } from "@/lib/queries";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { searchWindow } from "./filters";
import { ObjectSearchPreview } from "./ObjectSearchPreview";

interface SearchItem { id: number; kind: string; camera_serial: string; camera_name: string; location: string; title: string; timestamp: string; duration_seconds?: number | null; thumbnail_url?: string | null; href: string; is_protected: boolean }
interface SearchResponse { items: SearchItem[]; total: number; offset: number; limit: number }
interface SavedSearch { name: string; params: string }
const TYPES = [{ value: "", label: "All events", icon: Search }, { value: "person", label: "Person", icon: UserRound }, { value: "vehicle", label: "Vehicle", icon: Car }, { value: "motion", label: "Motion", icon: Footprints }, { value: "line_crossing", label: "Line crossing", icon: SlidersHorizontal }, { value: "tamper", label: "Tampering", icon: Lock }];
const RANGES = [
  { value: "hour", label: "Last hour" },
  { value: "day", label: "Last 24 hours" },
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "week", label: "Last 7 days" },
  { value: "all", label: "All available history" },
  { value: "custom", label: "Custom dates" },
  { value: "exact", label: "Exact times" },
];

function ResultImage({ item }: { item: SearchItem }) {
  const [failed, setFailed] = useState(false);
  return <div className="search-result-image relative flex aspect-video shrink-0 items-center justify-center overflow-hidden bg-muted text-muted-foreground">
    {item.thumbnail_url && !failed ? <img src={item.thumbnail_url} alt={`${item.title} at ${item.camera_name}`} loading="lazy" className="size-full object-cover" onError={() => setFailed(true)} /> : <div className="search-result-empty flex flex-col items-center gap-2">{item.kind === "recordings" ? <Film className="size-8" /> : <Image className="size-8" />}<span className="text-xs">{item.kind === "recordings" ? "Recorded footage" : "No preview available"}</span></div>}
    <span className="absolute left-2 top-2 rounded-md bg-card/95 px-2 py-1 text-xs font-semibold text-foreground">{item.title}</span>
    {item.is_protected && <span className="absolute right-2 top-2 rounded bg-card/95 p-1" title="Protected footage"><Lock className="size-4" /></span>}
    {item.href.startsWith("/playback?") && <span className="absolute bottom-2 right-2 flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground"><Play className="size-4" /></span>}
  </div>;
}

export function SearchPage() {
  const [params] = useSearchParams();
  const next = new URLSearchParams(params);
  if (params.get("mode") === "objects") {
    next.delete("mode");
    return <ObjectSearchPreview footageUrl={next.size ? `/search?${next}` : "/search"} />;
  }
  next.set("mode", "objects");
  return <FootageSearch objectSearchUrl={`/search?${next}`} />;
}

function FootageSearch({ objectSearchUrl }: { objectSearchUrl: string }) {
  const [params, setParams] = useSearchParams();
  const submittedQuery = params.get("q") || "";
  const [query, setQuery] = useState(submittedQuery);
  const [layoutChoice, setLayout] = useState<"grid" | "list" | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saved, setSaved] = useState<SavedSearch[]>([]);
  const user = useCurrentUser();
  const zone = useSiteTimeZone();
  const cameras = useCameras();
  const storageKey = `vizenlink_searches_${user?.id ?? "guest"}`;
  useEffect(() => {
    try { const value: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]"); setSaved(Array.isArray(value) ? value.filter((s): s is SavedSearch => typeof s?.name === "string" && typeof s?.params === "string").slice(0, 20) : []); } catch { setSaved([]); }
  }, [storageKey]);
  useEffect(() => setQuery(submittedQuery), [submittedQuery]);
  const kind = ["events", "recordings", "snapshots"].includes(params.get("kind") || "") ? params.get("kind")! : "events";
  const range = params.get("range") || "day";
  const selectedCameras = [...new Set(params.getAll("camera").filter(Boolean))];
  const eventType = params.get("event_type") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const fromKey = range === "exact" ? "from_time" : "from";
  const toKey = range === "exact" ? "to_time" : "to";
  const window = useMemo(() => searchWindow(range, zone, params.get(fromKey) || "", params.get(toKey) || ""), [range, zone, params, fromKey, toKey]);
  const requestParams = new URLSearchParams({ kind, limit: "24", offset: String(offset) });
  if (submittedQuery) requestParams.set("q", submittedQuery);
  for (const serial of selectedCameras) requestParams.append("camera_serials", serial);
  if (eventType && kind !== "snapshots") requestParams.set("event_type", eventType);
  if (window.start) requestParams.set("start_time", window.start);
  if (window.end) requestParams.set("end_time", window.end);
  const results = useQuery({ queryKey: ["search", requestParams.toString()], queryFn: ({ signal }) => apiFetch<SearchResponse>(`/api/v1/search?${requestParams}`, { signal }), enabled: !window.error });
  // Picture grid only when there are pictures: a grid of empty placeholders is mostly blank space.
  const layout = layoutChoice ?? (results.data?.items.some(item => item.thumbnail_url) ? "grid" : "list");
  const set = (key: string, value: string) => setParams(prev => { const next = new URLSearchParams(prev); next.delete("offset"); value ? next.set(key, value) : next.delete(key); if (key === "kind" && value === "snapshots") next.delete("event_type"); return next; });
  const setCameras = (serials: string[]) => setParams(prev => {
    const next = new URLSearchParams(prev);
    next.delete("offset");
    next.delete("camera");
    for (const serial of serials) next.append("camera", serial);
    return next;
  });
  const cameraLabel = selectedCameras.length === 0 ? "All accessible cameras" : selectedCameras.length === 1
    ? cameras.data?.find(c => c.serial === selectedCameras[0])?.name || selectedCameras[0]
    : `${selectedCameras.length} cameras`;
  const persist = (next: SavedSearch[]) => { try { localStorage.setItem(storageKey, JSON.stringify(next)); setSaved(next); return true; } catch { toast.error("Couldn't save this search in your browser."); return false; } };
  const save = () => { const name = saveName.trim(); if (!name) return; const nextParams = new URLSearchParams(params); nextParams.delete("offset"); if (persist([{ name, params: nextParams.toString() }, ...saved.filter(s => s.name !== name)].slice(0, 20))) { setSaveOpen(false); setSaveName(""); toast.success("Search saved in this browser."); } };
  return <div className="flex flex-col gap-6">
    <PageIntro description="Find indexed events, recordings and snapshots across your cameras."
      actions={<>
        <Button variant="outline" asChild><Link to={objectSearchUrl}><ScanSearch className="size-4" />Object Search preview</Link></Button>
        <Button variant="outline" onClick={() => setSaveOpen(true)}><Bookmark className="size-4" />Save search</Button>
        <Button variant="outline" asChild><Link to="/assistant"><ArrowUpRight className="size-4" />Ask the assistant</Link></Button>
      </>} />
    <div className="search-workspace overflow-hidden rounded-xl border border-border bg-card">
      <form className="flex items-center gap-2 border-b border-border p-4" onSubmit={e => { e.preventDefault(); set("q", query.trim()); setShowFilters(false); }}>
        <Search className="hidden size-6 shrink-0 text-primary sm:block" /><Input aria-label="Search footage" maxLength={100} placeholder="Search a camera name, location or alert type…" value={query} onChange={e => setQuery(e.target.value)} className="border-0 bg-transparent shadow-none" /><Button type="submit">Search</Button>
      </form>
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-4">
        <div className="flex max-w-full gap-4 overflow-x-auto" role="tablist" aria-label="Search collection">{[{ key: "events", title: "Alerts", icon: Footprints }, { key: "recordings", title: "Recordings", icon: Film }, { key: "snapshots", title: "Snapshots", icon: Image }].map(t => <button key={t.key} type="button" role="tab" aria-selected={kind === t.key} className={"search-collection-tab flex items-center gap-2 border-b-2 py-4 text-sm font-semibold " + (kind === t.key ? "border-primary text-primary-text" : "border-transparent text-muted-foreground")} onClick={() => set("kind", t.key)}><t.icon className="size-4" />{t.title}</button>)}</div>
        <Button variant="outline" size="sm" aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}><SlidersHorizontal className="size-4" />Filters</Button>
      </div>
      <div className="flex flex-col lg:flex-row">
        {showFilters && <aside className="search-filter-panel flex shrink-0 flex-col gap-6 border-b border-border p-4 lg:w-80 lg:border-r lg:border-b-0" aria-label="Search filters">
          <div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Refine results</span><Button variant="ghost" size="sm" onClick={() => { setParams({ kind }); setQuery(""); }}>Reset filters</Button></div>
          <label className="vms-field"><span className="flex items-center gap-2 font-semibold"><CalendarDays className="size-4" />When</span><NativeSelect aria-label="Search time range" className="w-full" value={range} onChange={e => set("range", e.target.value)}>{RANGES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</NativeSelect><span className="text-xs text-muted-foreground">Dates and times use {zone}</span></label>
          {range === "custom" && <div className="flex flex-col gap-2"><label className="vms-field">From date<Input type="date" aria-label="Search from date" value={params.get("from") || ""} onChange={e => set("from", e.target.value)} /></label><label className="vms-field">Through date<Input type="date" aria-label="Search through date" value={params.get("to") || ""} onChange={e => set("to", e.target.value)} /></label></div>}
          {range === "exact" && <div className="flex min-w-0 flex-col gap-2">
            <label className="vms-field">Start time<Input type="datetime-local" step={1} value={params.get(fromKey) || ""} onInput={e => set(fromKey, e.currentTarget.value)} /></label>
            <label className="vms-field">End time<Input type="datetime-local" step={1} value={params.get(toKey) || ""} onInput={e => set(toKey, e.currentTarget.value)} /></label>
          </div>}
          <fieldset className="min-w-0">
            <legend className="font-semibold">Cameras</legend>
            <Button variant="ghost" size="sm" aria-pressed={selectedCameras.length === 0} onClick={() => setCameras([])}>All accessible cameras</Button>
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto p-1">
              {cameras.data?.map(c => {
                const selected = selectedCameras.includes(c.serial);
                return <label key={c.serial} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-muted">
                  <Checkbox className="shrink-0 accent-primary" checked={selected}
                    onCheckedChange={checked => setCameras(checked === true ? [...selectedCameras, c.serial] : selectedCameras.filter(serial => serial !== c.serial))} />
                  <span className="min-w-0 wrap-anywhere">{c.name}</span>
                </label>;
              })}
            </div>
          </fieldset>
          {kind !== "snapshots" && <div className="flex flex-col gap-2"><span className="font-semibold">Alert type</span>{TYPES.map(t => <button type="button" key={t.value} aria-pressed={eventType === t.value} onClick={() => set("event_type", t.value)} className={"flex items-center gap-2 rounded-lg px-4 py-2 text-left text-sm " + (eventType === t.value ? "bg-selected font-semibold text-selected-foreground" : "text-muted-foreground hover:bg-muted")}><t.icon className="size-4" />{t.label}</button>)}</div>}
          {saved.length > 0 && <div className="flex flex-col gap-2 border-t border-border pt-4"><span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Saved searches</span>{saved.map(s => <div key={s.name} className="flex items-center gap-1"><button className="min-w-0 flex-1 truncate py-2 text-left text-sm hover:text-primary-text" onClick={() => setParams(new URLSearchParams(s.params))}><Bookmark className="mr-2 inline size-4" />{s.name}</button><Button variant="ghost" size="icon" aria-label={`Remove saved search ${s.name}`} onClick={() => persist(saved.filter(v => v.name !== s.name))}><X className="size-4" /></Button></div>)}</div>}
          <p className="text-xs leading-relaxed text-muted-foreground">Results come from the recorder’s index. Person and vehicle filters need matching alerts from your cameras. Visual attributes such as clothing color and license plates are not indexed.</p>
          <Button variant="outline" onClick={() => setShowFilters(false)}>Show results</Button>
        </aside>}
        <section className="flex min-w-0 flex-1 flex-col gap-4 p-4" aria-label="Search results" aria-live="polite">
          <div className="flex items-center justify-between gap-2"><span className="text-sm text-muted-foreground">{results.isFetching ? "Searching the index…" : `${results.data?.total ?? 0} results`}<span className="ml-2 hidden sm:inline">· {kind}</span></span><div className="flex gap-1"><Button variant={layout === "grid" ? "secondary" : "ghost"} size="icon" aria-label="Result grid" aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}><LayoutGrid className="size-4" /></Button><Button variant={layout === "list" ? "secondary" : "ghost"} size="icon" aria-label="Result list" aria-pressed={layout === "list"} onClick={() => setLayout("list")}><List className="size-4" /></Button></div></div>
          <p className="text-xs text-muted-foreground">{cameraLabel} · {RANGES.find(option => option.value === range)?.label ?? "Last 24 hours"}{eventType && kind !== "snapshots" ? ` · ${TYPES.find(type => type.value === eventType)?.label ?? eventType}` : ""}</p>
          {window.error && <p role="alert" className="rounded-lg bg-warning-subtle p-4 text-warning">{window.error}</p>}
          {results.error && <InlineError message={results.error.message} actionLabel="Retry search" onAction={() => void results.refetch()} />}
          {!window.error && results.isPending && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton className="h-48 rounded-xl" key={i} />)}</div>}
          {!window.error && !results.error && results.data?.items.length === 0 && <div className="flex min-h-80 flex-1 flex-col items-center justify-center gap-4 p-8 text-center"><span className="flex size-16 items-center justify-center rounded-2xl bg-selected text-primary"><Search className="size-8" /></span><h3 className="text-xl font-semibold">No matching moments yet</h3><p className="max-w-sm text-sm text-muted-foreground">Try a wider date range, another camera, or a different alert type. Only footage and alerts indexed by this recorder appear here.</p>{range !== "all" && <Button variant="outline" onClick={() => set("range", "all")}>Search all available history</Button>}</div>}
          {!window.error && <div className={layout === "grid" ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-3" : "flex flex-col gap-2"}>{results.data?.items.map(item => <Link key={`${item.kind}-${item.id}`} to={item.href} className={"search-result group overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary " + (layout === "list" ? "search-result-row flex items-center" : "")}>
            <ResultImage item={item} /><div className="search-result-body min-w-0 flex-1 p-4"><h3 className="truncate font-semibold">{item.camera_name}</h3><p className="mt-1 truncate text-xs text-muted-foreground">{item.location || item.camera_serial}</p><p className="mt-4 flex items-center gap-1 text-xs text-muted-foreground"><Clock className="size-4 shrink-0" />{formatDateTime(item.timestamp, zone, { second: undefined })}</p><span className="mt-2 flex items-center gap-1 text-xs font-semibold text-primary-text">{item.kind === "snapshots" ? "Open snapshot" : item.href.startsWith("/playback?") ? "Open playback" : "View event"}<ArrowUpRight className="size-4" /></span></div>
          </Link>)}</div>}
          {(results.data?.total ?? 0) > 24 && <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4"><span className="text-xs text-muted-foreground">{offset + 1}–{Math.min(offset + 24, results.data!.total)} of {results.data!.total}</span><div className="flex gap-2"><Button variant="outline" disabled={offset === 0} onClick={() => setParams(prev => { const next = new URLSearchParams(prev); next.set("offset", String(Math.max(0, offset - 24))); return next; })}>Previous results</Button><Button variant="outline" disabled={offset + 24 >= results.data!.total} onClick={() => setParams(prev => { const next = new URLSearchParams(prev); next.set("offset", String(offset + 24)); return next; })}>Next results</Button></div></div>}
        </section>
      </div>
    </div>
    <Dialog open={saveOpen} onOpenChange={setSaveOpen}><DialogContent><DialogHeader><DialogTitle>Save this search</DialogTitle><DialogDescription>Keep these filters in this browser for your account. Relative ranges update when you reopen a search.</DialogDescription></DialogHeader><form className="flex flex-col gap-4" onSubmit={e => { e.preventDefault(); save(); }}><label className="vms-field">Search name<Input autoFocus maxLength={64} value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="For example, entrance activity" /></label><Button type="submit" disabled={!saveName.trim()}>Save search filters</Button></form></DialogContent></Dialog>
  </div>;
}
