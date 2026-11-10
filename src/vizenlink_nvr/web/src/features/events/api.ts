import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface EventItem {
  id: number;
  camera_serial: string;
  event_type: string;
  source: string;
  start_time: string;
  end_time?: string | null;
  snapshot_path?: string | null;
  is_locked: boolean;
  clock_sync_state: string;
  raw_topic?: string | null;
  details?: Record<string, unknown> | null;
  created_at: string;
  // Phase 10 review workflow
  severity?: "critical" | "warning" | "info";
  review_state?: "new" | "acknowledged" | "resolved";
  reviewed_at?: string | null;
  reviewed_by?: string | null;
}

export interface EventListResponse {
  items: EventItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventFilters {
  camera_serial?: string;
  event_type?: string;
  start_time?: string;
  end_time?: string;
  is_locked?: boolean;
  severity?: string;
  review_state?: string;
  q?: string;
}

export function useEvents(filters: EventFilters, pageSize = 50) {
  return useInfiniteQuery<EventListResponse, Error>({
    queryKey: ["events", filters, pageSize],
    queryFn: async ({ pageParam = 0 }) => {
      const params = new URLSearchParams();
      params.set("limit", pageSize.toString());
      params.set("offset", (pageParam as number).toString());

      if (filters.camera_serial) params.set("camera_serial", filters.camera_serial);
      if (filters.event_type) params.set("event_type", filters.event_type);
      if (filters.start_time) params.set("start_time", filters.start_time);
      if (filters.end_time) params.set("end_time", filters.end_time);
      if (filters.is_locked !== undefined) params.set("is_locked", filters.is_locked.toString());
      if (filters.severity) params.set("severity", filters.severity);
      if (filters.review_state) params.set("review_state", filters.review_state);
      if (filters.q) params.set("q", filters.q);

      const res = await fetch(`/api/v1/events?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`Failed to load events: HTTP ${res.status}`);
      }
      return (await res.json()) as EventListResponse;
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
  });
}

export function useLockEvent() {
  const queryClient = useQueryClient();
  return useMutation<EventItem, Error, number>({
    mutationFn: async (eventId: number) => {
      const res = await fetch(`/api/v1/events/${eventId}/lock`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to lock event: HTTP ${res.status}`);
      }
      return (await res.json()) as EventItem;
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
    },
  });
}

export function useUnlockEvent() {
  const queryClient = useQueryClient();
  return useMutation<EventItem, Error, number>({
    mutationFn: async (eventId: number) => {
      const res = await fetch(`/api/v1/events/${eventId}/unlock`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to unlock event: HTTP ${res.status}`);
      }
      return (await res.json()) as EventItem;
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
    },
  });
}


export type ReviewAction = "acknowledge" | "resolve" | "reopen";

function invalidateEvents(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["events"] });
  void queryClient.invalidateQueries({ queryKey: ["event"] });
  void queryClient.invalidateQueries({ queryKey: ["recentEvents50"] });
}

/** Acknowledge / resolve / reopen one alert (shared state for every user). */
export function useReviewEvent() {
  const queryClient = useQueryClient();
  return useMutation<EventItem, Error, { id: number; action: ReviewAction }>({
    mutationFn: async ({ id, action }) => {
      const res = await fetch(`/api/v1/events/${id}/${action}`, { method: "POST" });
      if (!res.ok) throw new Error(`Failed to ${action} alert: HTTP ${res.status}`);
      return (await res.json()) as EventItem;
    },
    onSuccess: () => invalidateEvents(queryClient),
  });
}

/** Old VMS "Ack all": acknowledges every new alert matching the filters. */
export function useAcknowledgeAll() {
  const queryClient = useQueryClient();
  return useMutation<{ acknowledged: number }, Error, { camera_serial?: string; event_type?: string; severity?: string }>({
    mutationFn: async (body) => {
      const res = await fetch(`/api/v1/events/acknowledge-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Failed to acknowledge alerts: HTTP ${res.status}`);
      return (await res.json()) as { acknowledged: number };
    },
    onSuccess: () => invalidateEvents(queryClient),
  });
}

/** Old VMS "Delete": hides the alert; the event and its protected footage are kept. */
export function useHideEvent() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: async (id) => {
      const res = await fetch(`/api/v1/events/${id}/hide`, { method: "POST" });
      if (res.status === 409) throw new Error("This alert is locked to protect its footage. Unlock it before removing it.");
      if (!res.ok) throw new Error(`Failed to remove alert: HTTP ${res.status}`);
    },
    onSuccess: () => invalidateEvents(queryClient),
  });
}

export function useEvent(id: number | null) {
  return useQuery<EventItem, Error>({
    queryKey: ["event", id],
    enabled: id !== null && Number.isFinite(id),
    queryFn: async () => {
      const res = await fetch(`/api/v1/events/${id}`);
      if (!res.ok) throw new Error(`Failed to load alert: HTTP ${res.status}`);
      return (await res.json()) as EventItem;
    },
  });
}
