import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

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
