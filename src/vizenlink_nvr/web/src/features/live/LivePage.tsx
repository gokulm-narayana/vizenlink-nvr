import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Cctv,
  Plus,
  Search,
  Star,
  History,
  Settings,
  X,
  Save,
  Trash2,
  Maximize,
  Minimize,
  Camera,
  Expand,
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  Clock,
} from "lucide-react";
import { useCameras, useRecordingStatus, useCurrentUser } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { GridStorage, type GridDimension } from "@/services/grid_storage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineError } from "@/components/InlineError";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import {
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from "@/components/ui/context-menu";
import { useIsMobile } from "@/hooks/use-mobile";
import { toast } from "sonner";
import { cn } from "cn";
import { VideoTile } from "./VideoTile";
import { LIVE_COPY } from "./copy";

type SavedView = { name: string; serials: string[]; dimension: GridDimension };
type Preferences = { favorites: string[]; views: SavedView[] };

function readPreferences(key: string): Preferences {
  try {
    const data = JSON.parse(localStorage.getItem(key) || "{}");
    return {
      favorites: Array.isArray(data.favorites) ? data.favorites.filter((v: unknown) => typeof v === "string") : [],
      views: Array.isArray(data.views)
        ? data.views.filter(
            (v: SavedView) =>
              typeof v?.name === "string" &&
              Array.isArray(v.serials) &&
              v.serials.every((s) => typeof s === "string") &&
              [1, 2, 3, 4].includes(v.dimension)
          )
        : [],
    };
  } catch {
    return { favorites: [], views: [] };
  }
}

function readOrder(key: string): string[] {
  try {
    const data = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(data) ? data.filter((v: unknown) => typeof v === "string") : [];
  } catch {
    return [];
  }
}

/** Swap two serials in the channel order (old VMS "move CH x to CH y"). */
export function swapChannels(order: string[], a: string, b: string): string[] {
  const next = [...order];
  const i = next.indexOf(a);
  const j = next.indexOf(b);
  if (i < 0 || j < 0 || i === j) return next;
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

const LAYOUTS: GridDimension[] = [1, 2, 3, 4];
const OVERLAY_BTN = "size-8 rounded bg-video-overlay text-video-fg hover:bg-video-overlay hover:text-video-fg";

export const LivePage: React.FC = () => {
  const { data: rawCameras, isLoading, error, refetch } = useCameras();
  const { data: rawRecList } = useRecordingStatus();
  const cameras = useMemo(() => (Array.isArray(rawCameras) ? rawCameras : []), [rawCameras]);
  const user = useCurrentUser();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  // Fit-to-screen grid only on landscape screens; portrait tablets/phones get 16:9 tiles that scroll.
  const [isLandscape, setIsLandscape] = useState(() =>
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(orientation: landscape)").matches : true
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(orientation: landscape)");
    const onChange = () => setIsLandscape(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  const viewMode = useUiStore((s) => s.viewMode);
  const isManager = user?.role === "operator" || user?.role === "owner";

  const storageKey = `vizenlink_live_preferences_${user?.id ?? "guest"}`;
  const orderKey = `vizenlink_live_order_${user?.id ?? "guest"}`;
  const [preferences, setPreferences] = useState(() => readPreferences(storageKey));
  const [order, setOrder] = useState<string[]>(() => readOrder(orderKey));
  useEffect(() => {
    setPreferences(readPreferences(storageKey));
    setOrder(readOrder(orderKey));
  }, [storageKey, orderKey]);

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
  const [draftSelection, setDraftSelection] = useState<string[]>([]);
  const [dragSerial, setDragSerial] = useState<string | null>(null);
  useEffect(() => {
    setMaximizedSerial(null);
  }, [search, group, favoritesOnly, selection]);

  // Whole-grid fullscreen (old VMS "layout full screen").
  const rootRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  useEffect(() => {
    const onChange = () => setIsFullscreen(rootRef.current !== null && document.fullscreenElement === rootRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleGridFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen?.();
    else void rootRef.current?.requestFullscreen?.();
  };

  const persist = (next: Preferences) => {
    setPreferences(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      toast.error("Your browser couldn't save this preference. It will last for this visit only.");
    }
  };

  // Stable channel order: saved order first, then any new cameras in API order.
  const ordered = useMemo(() => {
    const rank = new Map(order.map((s, i) => [s, i]));
    const pos = (serial: string, apiIndex: number) => rank.get(serial) ?? 1e6 + apiIndex;
    return cameras
      .map((c, i) => ({ c, k: pos(c.serial, i) }))
      .sort((a, b) => a.k - b.k)
      .map((x) => x.c);
  }, [cameras, order]);
  const channelOf = useCallback((serial: string) => ordered.findIndex((c) => c.serial === serial) + 1, [ordered]);

  const moveChannel = (from: string, to: string) => {
    const next = swapChannels(
      ordered.map((c) => c.serial),
      from,
      to
    );
    setOrder(next);
    try {
      localStorage.setItem(orderKey, JSON.stringify(next));
    } catch {
      // Not persisted; applies for this visit.
    }
    toast.success(`Moved to CH ${next.indexOf(from) + 1}`);
  };

  const groups = [...new Set(cameras.map((c) => c.group_tag || c.location).filter(Boolean))].sort();
  const filtered = ordered.filter(
    (c) =>
      (!selection || selection.includes(c.serial)) &&
      (!group || (c.group_tag || c.location) === group) &&
      (!favoritesOnly || preferences.favorites.includes(c.serial)) &&
      `${c.name} ${c.location || ""} ${c.group_tag || ""} ${c.serial}`.toLowerCase().includes(search.toLowerCase())
  );
  // Only confirmed recording shows REC (policy alone is not proof).
  const recordingSet = useMemo(() => {
    const s = new Set<string>();
    for (const r of Array.isArray(rawRecList) ? rawRecList : []) if (r.is_recording === true) s.add(r.camera_serial);
    return s;
  }, [rawRecList]);

  const perPage = dimension * dimension;
  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const currentPage = Math.min(page, totalPages - 1);
  const visible = filtered.slice(currentPage * perPage, (currentPage + 1) * perPage);
  const expanded = cameras.find((c) => c.serial === maximizedSerial);
  const isFiltered = Boolean(search || group || favoritesOnly || selection);

  const resetFilters = () => {
    setSearch("");
    setGroup("");
    setFavoritesOnly(false);
    setSelectedView("");
    setSelection(null);
    setPage(0);
  };
  const changeLayout = (dim: GridDimension) => {
    setDimension(dim);
    setPage(0);
    GridStorage.save({ dimension: dim, page: 0, slotAssignments: {} });
  };
  const changePage = (p: number) => {
    setPage(p);
    GridStorage.save({ dimension, page: p, slotAssignments: {} });
  };
  const selectView = (name: string) => {
    resetFilters();
    setSelectedView(name);
    const view = preferences.views.find((v) => v.name === name);
    if (view) {
      setSelection(view.serials);
      changeLayout(view.dimension);
    }
  };
  const saveView = () => {
    const name = viewName.trim();
    if (!name || !filtered.length) return;
    if (preferences.views.some((v) => v.name.toLowerCase() === name.toLowerCase())) {
      toast.error("Choose a different name. A view with that name already exists.");
      return;
    }
    persist({ ...preferences, views: [...preferences.views, { name, serials: filtered.map((c) => c.serial), dimension }] });
    setSelection(filtered.map((c) => c.serial));
    setSelectedView(name);
    setSaveOpen(false);
    setViewName("");
    toast.success("View saved on this browser");
  };
  const toggleFavorite = (serial: string) =>
    persist({
      ...preferences,
      favorites: preferences.favorites.includes(serial)
        ? preferences.favorites.filter((s) => s !== serial)
        : [...preferences.favorites, serial],
    });

  if (isLoading)
    return (
      <div className="grid gap-4 p-4 sm:grid-cols-2" aria-label="Loading cameras">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="aspect-video" />
        ))}
      </div>
    );
  if (error) return <InlineError message="Couldn't load your cameras." actionLabel="Reload cameras" onAction={() => void refetch()} />;
  if (!cameras.length)
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
        <div className="rounded-xl bg-selected p-6 text-primary-text">
          <Cctv className="size-10" />
        </div>
        <h2 className="text-xl font-semibold">{isManager ? LIVE_COPY.EMPTY_HEADING_OPERATOR : LIVE_COPY.EMPTY_HEADING_VIEWER}</h2>
        <p className="max-w-md text-muted-foreground">{isManager ? LIVE_COPY.EMPTY_BODY_OPERATOR : LIVE_COPY.EMPTY_BODY_VIEWER}</p>
        {isManager && (
          <Button asChild>
            <Link to="/cameras/add">
              <Plus className="size-4" />
              Add camera
            </Link>
          </Button>
        )}
      </div>
    );

  const fitToScreen = !isMobile && isLandscape;
  const cols = expanded ? 1 : dimension;
  const cells: Array<(typeof cameras)[number] | null> = expanded
    ? [expanded]
    : fitToScreen && !isFiltered
      ? [...visible, ...Array<null>(Math.max(0, perPage - visible.length)).fill(null)]
      : visible;

  return (
    <div
      ref={rootRef}
      className={cn("flex min-w-0 flex-col gap-2 bg-background", isFullscreen && "p-2")}
      // dynamic-style: fit the grid to the viewport below the app header (or the whole screen in fullscreen).
      style={fitToScreen ? { height: isFullscreen ? "100dvh" : "calc(100dvh - 4.5rem)" } : undefined}
    >
      {/* One toolbar row (wraps on small screens). */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2">
        <ToggleGroup
          type="single"
          value={dimension.toString()}
          onValueChange={(v) => v && changeLayout(parseInt(v, 10) as GridDimension)}
          variant="outline"
          size="sm"
          aria-label="Grid layout"
        >
          {LAYOUTS.map((dim) => (
            <ToggleGroupItem key={dim} value={dim.toString()} aria-label={`${dim} by ${dim} grid`} className="px-2 text-xs font-semibold">
              {dim}×{dim}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <div className="relative min-w-40 flex-1 basis-40 sm:max-w-64">
          <Search className="absolute left-2 top-2 size-4 text-muted-foreground" />
          <Input
            aria-label="Search cameras"
            placeholder="Search cameras…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="h-8 pl-8"
          />
        </div>

        {groups.length > 0 && (
          <select
            aria-label="Camera group"
            className="vms-select h-8 py-0"
            value={group}
            onChange={(e) => {
              setGroup(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All locations</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        )}

        <Button
          size="sm"
          variant={favoritesOnly ? "secondary" : "outline"}
          aria-pressed={favoritesOnly}
          onClick={() => {
            setFavoritesOnly(!favoritesOnly);
            setPage(0);
          }}
        >
          <Star className={cn("size-4", favoritesOnly && "fill-primary text-primary")} />
          Favorites
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setDraftSelection(selection || cameras.map((c) => c.serial));
            setChooseOpen(true);
          }}
        >
          Choose cameras
        </Button>

        <label htmlFor="saved-view" className="sr-only">
          Saved views
        </label>
        <select id="saved-view" className="vms-select h-8 py-0" value={selectedView} onChange={(e) => selectView(e.target.value)}>
          <option value="">All cameras</option>
          {preferences.views.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name}
            </option>
          ))}
        </select>
        <Button size="sm" variant="ghost" disabled={!filtered.length} onClick={() => setSaveOpen(true)} aria-label="Save current view">
          <Save className="size-4" />
          <span className="hidden xl:inline">Save view</span>
        </Button>
        {selectedView && (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Delete saved view ${selectedView}`}
            onClick={() => {
              persist({ ...preferences, views: preferences.views.filter((v) => v.name !== selectedView) });
              resetFilters();
            }}
          >
            <Trash2 className="size-4" />
          </Button>
        )}
        {isFiltered && (
          <Button size="sm" variant="ghost" onClick={resetFilters}>
            Show all
          </Button>
        )}

        <div className="ml-auto flex items-center gap-2">
          {totalPages > 1 && !expanded && (
            <div className="flex items-center gap-1">
              <Button aria-label={LIVE_COPY.PREV_PAGE} variant="outline" size="icon" className="size-8" disabled={currentPage <= 0} onClick={() => changePage(Math.max(0, currentPage - 1))}>
                <ChevronLeft className="size-4" />
              </Button>
              <span className="px-1 text-xs text-muted-foreground">{LIVE_COPY.PAGE_INDICATOR(currentPage + 1, totalPages)}</span>
              <Button aria-label={LIVE_COPY.NEXT_PAGE} variant="outline" size="icon" className="size-8" disabled={currentPage >= totalPages - 1} onClick={() => changePage(Math.min(totalPages - 1, currentPage + 1))}>
                <ChevronRight className="size-4" />
              </Button>
            </div>
          )}
          <span className="hidden text-xs text-muted-foreground sm:inline">{LIVE_COPY.CAMERAS_COUNT(filtered.length)}</span>
          {expanded && (
            <Button size="sm" variant="outline" onClick={() => setMaximizedSerial(null)}>
              <X className="size-4" />
              Back to grid
            </Button>
          )}
          {isManager && !isFullscreen && (
            <Button size="sm" asChild>
              <Link to="/cameras/add" aria-label="Add camera">
                <Plus className="size-4" />
                <span className="hidden lg:inline">Add camera</span>
              </Link>
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={toggleGridFullscreen} aria-label={isFullscreen ? "Exit full screen" : "Full screen grid"}>
            {isFullscreen ? <Minimize className="size-4" /> : <Maximize className="size-4" />}
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-lg border border-border bg-card p-12 text-center">
          <Search className="size-8 text-muted-foreground" />
          <h3 className="font-semibold">No cameras in this view</h3>
          <p className="text-muted-foreground">Try another search, or add cameras to your favorites.</p>
          <Button variant="outline" onClick={resetFilters}>
            Show all cameras
          </Button>
        </div>
      ) : (
        <div
          data-slot="live-grid"
          className={cn(
            "grid min-h-0 gap-1",
            fitToScreen ? "flex-1" : dimension === 1 || expanded ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"
          )}
          // dynamic-style: N×N grid that fills the available height (old VMS multiview).
          style={fitToScreen ? { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${cols}, minmax(0, 1fr))` } : undefined}
        >
          {cells.map((cam, idx) => {
            if (!cam) {
              const ch = currentPage * perPage + idx + 1;
              return (
                <div
                  key={`empty-${ch}`}
                  className="flex min-h-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border bg-card text-xs text-muted-foreground"
                >
                  <span className="font-semibold tabular-nums">CH {ch}</span>
                  <span>Empty channel</span>
                </div>
              );
            }
            const fav = preferences.favorites.includes(cam.serial);
            const playbackHref = `/playback?camera=${encodeURIComponent(cam.serial)}`;
            const last5Href = `${playbackHref}&t=${encodeURIComponent(new Date(Date.now() - 300000).toISOString())}`;
            const channel = channelOf(cam.serial);
            return (
              <div key={cam.serial} className="min-h-0 min-w-0">
                <VideoTile
                  serial={cam.serial}
                  name={cam.name}
                  channel={channel}
                  fill={fitToScreen}
                  isRecording={recordingSet.has(cam.serial)}
                  isMaximized={!!expanded}
                  lastSeenAt={cam.last_seen_at}
                  viewMode={viewMode}
                  onToggleMaximize={() => setMaximizedSerial(expanded ? null : cam.serial)}
                  onDragStartTile={() => setDragSerial(cam.serial)}
                  onDropTile={() => {
                    if (dragSerial && dragSerial !== cam.serial) moveChannel(dragSerial, cam.serial);
                    setDragSerial(null);
                  }}
                  actions={
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={OVERLAY_BTN}
                        aria-label={`${fav ? "Remove" : "Add"} ${cam.name} ${fav ? "from" : "to"} favorites`}
                        aria-pressed={fav}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFavorite(cam.serial);
                        }}
                      >
                        <Star className={cn("size-4", fav && "fill-warning text-warning")} />
                      </Button>
                      <Button variant="ghost" size="icon" aria-label="Playback" className={OVERLAY_BTN} asChild>
                        <Link aria-label="Playback" to={playbackHref}>
                          <History className="size-4" />
                        </Link>
                      </Button>
                      {isManager && (
                        <Button variant="ghost" size="icon" aria-label={`Settings for ${cam.name}`} className={OVERLAY_BTN} asChild>
                          <Link aria-label={`Settings for ${cam.name}`} to={`/cameras/${encodeURIComponent(cam.serial)}`}>
                            <Settings className="size-4" />
                          </Link>
                        </Button>
                      )}
                    </>
                  }
                  renderMenu={(tile) => (
                    <>
                      <ContextMenuLabel>
                        CH {channel} · {cam.name}
                      </ContextMenuLabel>
                      <ContextMenuItem onSelect={tile.fullscreen}>
                        <Expand />
                        Full screen
                      </ContextMenuItem>
                      <ContextMenuItem onSelect={() => setMaximizedSerial(expanded ? null : cam.serial)}>
                        <Maximize />
                        {expanded ? "Back to grid" : "Enlarge in grid"}
                      </ContextMenuItem>
                      <ContextMenuItem onSelect={tile.snapshot}>
                        <Camera />
                        Take snapshot
                      </ContextMenuItem>
                      <ContextMenuSeparator />
                      <ContextMenuItem onSelect={() => void navigate(playbackHref)}>
                        <History />
                        Open playback
                      </ContextMenuItem>
                      <ContextMenuItem onSelect={() => void navigate(last5Href)}>
                        <Clock />
                        Replay last 5 minutes
                      </ContextMenuItem>
                      <ContextMenuItem onSelect={() => toggleFavorite(cam.serial)}>
                        <Star />
                        {fav ? "Remove from favorites" : "Add to favorites"}
                      </ContextMenuItem>
                      {ordered.length > 1 && (
                        <ContextMenuSub>
                          <ContextMenuSubTrigger>
                            <ArrowLeftRight />
                            Move to channel
                          </ContextMenuSubTrigger>
                          <ContextMenuSubContent>
                            {ordered.map((other, i) =>
                              other.serial === cam.serial ? null : (
                                <ContextMenuItem key={other.serial} onSelect={() => moveChannel(cam.serial, other.serial)}>
                                  CH {i + 1} · {other.name}
                                </ContextMenuItem>
                              )
                            )}
                          </ContextMenuSubContent>
                        </ContextMenuSub>
                      )}
                      {isManager && (
                        <>
                          <ContextMenuSeparator />
                          <ContextMenuItem onSelect={() => void navigate(`/cameras/${encodeURIComponent(cam.serial)}`)}>
                            <Settings />
                            Camera settings
                          </ContextMenuItem>
                        </>
                      )}
                    </>
                  )}
                />
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save this camera view</DialogTitle>
            <DialogDescription>Save the {filtered.length} selected cameras and grid layout on this browser.</DialogDescription>
          </DialogHeader>
          <label className="vms-field">
            View name
            <Input
              autoFocus
              maxLength={60}
              placeholder="e.g. Entrances"
              value={viewName}
              onChange={(e) => setViewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveView();
              }}
            />
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveOpen(false)}>
              Don&apos;t save
            </Button>
            <Button disabled={!viewName.trim()} onClick={saveView}>
              Save view
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={chooseOpen} onOpenChange={setChooseOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Choose cameras</DialogTitle>
            <DialogDescription>Select the cameras you want to watch together.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setDraftSelection(cameras.map((c) => c.serial))}>
              Select all
            </Button>
            <Button variant="ghost" onClick={() => setDraftSelection([])}>
              Clear selection
            </Button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {ordered.map((c) => (
              <label key={c.serial} className="flex cursor-pointer items-center gap-4 border-b border-border py-4">
                <input
                  type="checkbox"
                  checked={draftSelection.includes(c.serial)}
                  onChange={(e) =>
                    setDraftSelection(e.target.checked ? [...draftSelection, c.serial] : draftSelection.filter((s) => s !== c.serial))
                  }
                />
                <span>
                  CH {channelOf(c.serial)} · {c.name}
                  <span className="block text-xs text-muted-foreground">{c.location || c.serial}</span>
                </span>
              </label>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setChooseOpen(false)}>
              Keep current cameras
            </Button>
            <Button
              disabled={!draftSelection.length}
              onClick={() => {
                resetFilters();
                setSelection(draftSelection);
                setChooseOpen(false);
              }}
            >
              Show {draftSelection.length} cameras
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LivePage;
