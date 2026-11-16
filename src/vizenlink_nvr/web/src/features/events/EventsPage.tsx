import React, { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router";
import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import type { DateRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import { useCameras } from "@/lib/queries";
import { useSiteTimeZone, zonedDayBounds } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { useAcknowledgeAll, useEvents, type EventItem, type EventFilters as ApiEventFilters } from "./api";
import { EventFilters } from "./EventFilters";
import { EventCard } from "./EventCard";
import { EventSheet } from "./EventSheet";
import { EVENTS_COPY } from "./copy";
import { PageIntro } from "@/components/PageIntro";

function formatDateToIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export const EventsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const siteZone = useSiteTimeZone();
  const viewMode = useUiStore((s) => s.viewMode);
  const readEventIds = useUiStore((s) => s.readEventIds);
  const markEventRead = useUiStore((s) => s.markEventRead);

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

  // Read filter state from URL search params
  const selectedCamera = searchParams.get("camera") || "";
  const selectedType = searchParams.get("type") || "";
  const fromParam = searchParams.get("from") || "";
  const toParam = searchParams.get("to") || "";
  const severityParam = searchParams.get("severity") || "";
  const statusParam = searchParams.get("status") || "open";
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);
  const ackAll = useAcknowledgeAll();

  const [unreadOnly, setUnreadOnly] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null);

  // Parse date range from URL params
  const dateRange: DateRange | undefined = useMemo(() => {
    if (!fromParam) return undefined;
    const from = new Date(`${fromParam}T00:00:00`);
    const to = toParam ? new Date(`${toParam}T00:00:00`) : undefined;
    return { from, to };
  }, [fromParam, toParam]);

  // Convert date bounds to site-zone ISO strings
  const apiFilters = useMemo<ApiEventFilters>(() => {
    const filters: ApiEventFilters = {};
    if (selectedCamera) filters.camera_serial = selectedCamera;
    if (selectedType) filters.event_type = selectedType;
    if (severityParam) filters.severity = severityParam;
    if (statusParam !== "all") filters.review_state = statusParam;
    if (debouncedSearch) filters.q = debouncedSearch;

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
      // If single day selected
      try {
        const [, end] = zonedDayBounds(fromParam, siteZone);
        filters.end_time = end.toISOString();
      } catch {
        // fallback
      }
    }
    return filters;
  }, [selectedCamera, selectedType, fromParam, toParam, siteZone, severityParam, statusParam, debouncedSearch]);

  const {
    data,
    error,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useEvents(apiFilters);

  // Flatten infinite query pages
  const allItems = useMemo(() => {
    if (!data?.pages) return [];
    return data.pages.flatMap((page) => page.items);
  }, [data]);

  const total = data?.pages[0]?.total ?? 0;

  // Filter client-side by unread if active in Advanced view
  const displayedItems = useMemo(() => {
    if (unreadOnly) {
      return allItems.filter((evt) => !readEventIds.has(evt.id));
    }
    return allItems;
  }, [allItems, viewMode, unreadOnly, readEventIds]);

  const isFiltered = Boolean(
    selectedCamera || selectedType || fromParam || toParam || unreadOnly || severityParam || debouncedSearch || statusParam !== "open"
  );
  const setParam = (key: string, value: string, defaultValue = "") =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value && value !== defaultValue) next.set(key, value);
      else next.delete(key);
      return next;
    });

  // Filter Handlers
  const handleCameraChange = (serial: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (serial) next.set("camera", serial);
      else next.delete("camera");
      return next;
    });
  };

  const handleTypeChange = (type: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (type) next.set("type", type);
      else next.delete("type");
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
      next.delete("type");
      next.delete("from");
      next.delete("to");
      next.delete("severity");
      next.delete("status");
      next.delete("q");
      return next;
    });
    setSearch("");
    setUnreadOnly(false);
  };

  const handleCardClick = (event: EventItem) => {
    markEventRead(event.id);
    setSelectedEvent(event);
  };

  return (
    <div className="flex min-h-full flex-col gap-6">
      <PageIntro description="Review camera events, investigate the footage, and keep your team up to date." />
      {/* Filter Bar & Summary */}
      <section
        aria-label="Alert filters and actions"
        className="sticky top-16 z-20 flex max-h-[45dvh] shrink-0 flex-col gap-4 overflow-y-auto bg-background py-2"
      >
        <div className="flex flex-wrap items-center justify-end gap-4">
          {total > 0 && (
            <span className="text-xs font-normal text-muted-foreground">
              Total events: <strong className="text-foreground">{total}</strong>
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={ackAll.isPending}
            onClick={() =>
              ackAll.mutate(
                {
                  camera_serial: selectedCamera || undefined,
                  event_type: selectedType || undefined,
                  severity: severityParam || undefined,
                },
                {
                  onSuccess: (r) =>
                    toast.success(r.acknowledged ? `Acknowledged ${r.acknowledged} alerts` : "No new alerts to acknowledge"),
                  onError: (e) => toast.error(e.message),
                }
              )
            }
          >
            <CheckCheck className="size-4" />
            Acknowledge all
          </Button>
        </div>

        <EventFilters
          cameras={cameras}
          selectedCamera={selectedCamera}
          selectedType={selectedType}
          dateRange={dateRange}
          unreadOnly={unreadOnly}
          onCameraChange={handleCameraChange}
          onTypeChange={handleTypeChange}
          onDateRangeChange={handleDateRangeChange}
          onUnreadOnlyChange={setUnreadOnly}
          onClearFilters={handleClearFilters}
          isFiltered={isFiltered}
          zone={siteZone}
          search={search}
          onSearchChange={(q) => {
            setSearch(q);
            setParam("q", q.trim());
          }}
          severity={severityParam}
          onSeverityChange={(v) => setParam("severity", v)}
          status={statusParam}
          onStatusChange={(v) => setParam("status", v, "open")}
        />
      </section>

      {/* Load Error State */}
      {error && (
        <InlineError
          message={EVENTS_COPY.LOAD_ERROR_MESSAGE}
          actionLabel={EVENTS_COPY.LOAD_ERROR_ACTION}
          onAction={() => void refetch()}
        />
      )}

      {/* Loading Skeleton Grid */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col rounded-md border border-border bg-card overflow-hidden"
            >
              <Skeleton className="aspect-video w-full rounded-none" />
              <div className="p-4 flex flex-col gap-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-1/4" />
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
              <Bell className="h-6 w-6 text-muted-foreground" />
            </EmptyMedia>
            <EmptyTitle>
              {isFiltered
                ? EVENTS_COPY.EMPTY_NO_MATCH_TITLE
                : EVENTS_COPY.EMPTY_NO_EVENTS_TITLE}
            </EmptyTitle>
            <EmptyDescription>
              {isFiltered
                ? EVENTS_COPY.EMPTY_NO_MATCH_DESCRIPTION
                : EVENTS_COPY.EMPTY_NO_EVENTS_DESCRIPTION}
            </EmptyDescription>
          </Empty>
        </div>
      )}

      {/* Event Cards Grid */}
      {!isLoading && displayedItems.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {displayedItems.map((evt) => (
            <EventCard
              key={evt.id}
              event={evt}
              cameraName={cameraMap.get(evt.camera_serial)}
              isRead={readEventIds.has(evt.id)}
              onClick={handleCardClick}
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
              EVENTS_COPY.LOAD_MORE
            )}
          </Button>
        </div>
      )}

      {/* Event Details Sheet */}
      <EventSheet
        event={selectedEvent}
        cameraName={selectedEvent ? cameraMap.get(selectedEvent.camera_serial) : undefined}
        isOpen={Boolean(selectedEvent)}
        onClose={() => setSelectedEvent(null)}
        zone={siteZone}
      />
    </div>
  );
};

export default EventsPage;
