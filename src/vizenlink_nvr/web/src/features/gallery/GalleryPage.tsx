import React, { useState, useMemo } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { PageIntro } from "@/components/PageIntro";
import { Images } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { useCameras, useCurrentUser } from "@/lib/queries";
import { useSiteTimeZone, zonedDayBounds } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { useGallery, type GalleryItem, type GalleryFilters as ApiGalleryFilters } from "./api";
import { GalleryFilters } from "./GalleryFilters";
import { GalleryCard } from "./GalleryCard";
import { PreviewDialog } from "./PreviewDialog";
import { GALLERY_COPY } from "./copy";

function formatDateToIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export const GalleryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const siteZone = useSiteTimeZone();
  const viewMode = useUiStore((s) => s.viewMode);
  const currentUser = useCurrentUser();

  const { data: rawCameras = [] } = useCameras();
  const cameras = useMemo(
    () => rawCameras.map((c) => ({ serial: c.serial, name: c.name })),
    [rawCameras]
  );
  const cameraMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of cameras) {
      map.set(c.serial, c.name);
    }
    return map;
  }, [cameras]);

  // Tab state: "snapshots" | "clips" synced with ?tab=
  const activeTab = searchParams.get("tab") === "clips" ? "clips" : "snapshots";

  // Filter params
  const selectedCamera = searchParams.get("camera") || "";
  const fromParam = searchParams.get("from") || "";
  const toParam = searchParams.get("to") || "";
  const [selectedUser, setSelectedUser] = useState("all");

  const [previewItem, setPreviewItem] = useState<GalleryItem | null>(null);
  const linkedItemId = Number(searchParams.get("item"));
  const linkedItem = useQuery({
    queryKey: ["gallery", "item", linkedItemId],
    queryFn: () => apiFetch<GalleryItem>(`/api/v1/gallery/${linkedItemId}`),
    enabled: Number.isInteger(linkedItemId) && linkedItemId > 0,
  });
  const activePreview = previewItem || linkedItem.data || null;

  // Parse date range
  const dateRange: DateRange | undefined = useMemo(() => {
    if (!fromParam) return undefined;
    const from = new Date(`${fromParam}T00:00:00`);
    const to = toParam ? new Date(`${toParam}T00:00:00`) : undefined;
    return { from, to };
  }, [fromParam, toParam]);

  // API filters
  const apiFilters = useMemo<ApiGalleryFilters>(() => {
    const filters: ApiGalleryFilters = {};
    if (selectedCamera) filters.camera_serial = selectedCamera;

    if (fromParam) {
      try {
        const [start] = zonedDayBounds(fromParam, siteZone);
        filters.start_time = start.toISOString();
      } catch {
        // fallback
      }
    }
    if (toParam) {
      try {
        const [, end] = zonedDayBounds(toParam, siteZone);
        filters.end_time = end.toISOString();
      } catch {
        // fallback
      }
    } else if (fromParam) {
      try {
        const [, end] = zonedDayBounds(fromParam, siteZone);
        filters.end_time = end.toISOString();
      } catch {
        // fallback
      }
    }
    return filters;
  }, [selectedCamera, fromParam, toParam, siteZone]);

  const {
    data,
    error,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useGallery(apiFilters);

  // Flatten infinite items
  const allItems = useMemo(() => {
    if (!data?.pages) return [];
    return data.pages.flatMap((page) => page.items);
  }, [data]);

  // Filter items by active tab and client-side user filter
  const displayedItems = useMemo(() => {
    return allItems.filter((item) => {
      // Tab filter
      const isSnapshot = item.item_type === "snapshot";
      if (activeTab === "snapshots" && !isSnapshot) return false;
      if (activeTab === "clips" && isSnapshot) return false;

      // User filter (Advanced view)
      if (viewMode === "advanced" && selectedUser !== "all") {
        if (selectedUser === "me") {
          if (item.user_id !== currentUser?.id) return false;
        } else {
          if (item.user_id !== Number(selectedUser)) return false;
        }
      }

      return true;
    });
  }, [allItems, activeTab, viewMode, selectedUser, currentUser?.id]);

  const isFiltered = Boolean(
    selectedCamera || fromParam || toParam || (viewMode === "advanced" && selectedUser !== "all")
  );

  // Handlers
  const handleTabChange = (val: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (val === "clips") next.set("tab", "clips");
      else next.delete("tab");
      return next;
    });
  };

  const handleCameraChange = (serial: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (serial) next.set("camera", serial);
      else next.delete("camera");
      return next;
    });
  };

  const handleDateRangeChange = (range: DateRange | undefined) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (range?.from) {
        next.set("from", formatDateToIso(range.from));
      } else {
        next.delete("from");
      }
      if (range?.to) {
        next.set("to", formatDateToIso(range.to));
      } else {
        next.delete("to");
      }
      return next;
    });
  };

  const handleClearFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("camera");
      next.delete("from");
      next.delete("to");
      return next;
    });
    setSelectedUser("all");
  };

  return (
    <div className="flex flex-col gap-6 min-h-full">
      <PageIntro description="Browse saved snapshots and clips. Open a moment to review, download or return to its recording." />
      {linkedItem.error && <InlineError message={linkedItem.error.message} actionLabel="Reload snapshot" onAction={() => void linkedItem.refetch()} />}
      {/* Top Controls: Tabs & Filter Bar */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Tabs value={activeTab} onValueChange={handleTabChange}>
            <TabsList>
              <TabsTrigger value="snapshots" className="text-xs font-semibold">
                {GALLERY_COPY.TAB_SNAPSHOTS}
              </TabsTrigger>
              <TabsTrigger value="clips" className="text-xs font-semibold">
                {GALLERY_COPY.TAB_CLIPS}
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {displayedItems.length > 0 && (
            <span className="text-xs font-normal text-muted-foreground">
              Total {activeTab}: <strong className="text-foreground">{displayedItems.length}</strong>
            </span>
          )}
        </div>

        <GalleryFilters
          cameras={cameras}
          selectedCamera={selectedCamera}
          dateRange={dateRange}
          selectedUser={selectedUser}
          onCameraChange={handleCameraChange}
          onDateRangeChange={handleDateRangeChange}
          onUserChange={setSelectedUser}
          onClearFilters={handleClearFilters}
          isFiltered={isFiltered}
          zone={siteZone}
        />
      </div>

      {/* Load Error State */}
      {error && (
        <InlineError
          message={GALLERY_COPY.LOAD_ERROR_MESSAGE}
          actionLabel={GALLERY_COPY.LOAD_ERROR_ACTION}
          onAction={() => void refetch()}
        />
      )}

      {/* Loading Skeleton Grid */}
      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col rounded-md border border-border bg-card overflow-hidden"
            >
              <Skeleton className="aspect-video w-full rounded-none" />
              <div className="p-4 flex flex-col gap-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && displayedItems.length === 0 && (
        <div className="flex flex-1 items-center justify-center p-8">
          <Empty className="border border-dashed border-border bg-card/50">
            <EmptyMedia>
              <Images className="h-6 w-6 text-muted-foreground" />
            </EmptyMedia>
            <EmptyTitle>{GALLERY_COPY.EMPTY_TITLE}</EmptyTitle>
            <EmptyDescription>{GALLERY_COPY.EMPTY_DESCRIPTION}</EmptyDescription>
          </Empty>
        </div>
      )}

      {/* Gallery Cards Grid */}
      {!isLoading && displayedItems.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {displayedItems.map((item) => (
            <GalleryCard
              key={item.id}
              item={item}
              cameraName={cameraMap.get(item.camera_serial)}
              onClick={setPreviewItem}
              zone={siteZone}
            />
          ))}
        </div>
      )}

      {/* Load More Button */}
      {hasNextPage && (
        <div className="flex justify-center py-4">
          <Button
            variant="outline"
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
            className="h-9 px-6 text-xs font-semibold"
          >
            {isFetchingNextPage ? (
              <>
                <Spinner className="mr-2 h-4 w-4" />
                <span>Loading...</span>
              </>
            ) : (
              GALLERY_COPY.LOAD_MORE
            )}
          </Button>
        </div>
      )}

      {/* Preview Dialog */}
      <PreviewDialog
        item={activePreview}
        cameraName={activePreview ? cameraMap.get(activePreview.camera_serial) : undefined}
        isOpen={Boolean(activePreview)}
        onClose={() => { setPreviewItem(null); if (searchParams.has("item")) setSearchParams(prev => { const next = new URLSearchParams(prev); next.delete("item"); return next; }, { replace: true }); }}
        zone={siteZone}
      />
    </div>
  );
};

export default GalleryPage;
