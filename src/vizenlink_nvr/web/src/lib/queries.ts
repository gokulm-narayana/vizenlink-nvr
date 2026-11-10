import React from "react";
import { QueryClient, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import { useUiStore } from "@/stores/ui";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  permissions: string[];
}

export interface AuthStatus {
  initialized: boolean;
  authenticated: boolean;
  user?: AuthUser | null;
  site_timezone: string | null;
}

export interface CameraInfo {
  id: number;
  serial: string;
  name: string;
  rtsp_url?: string;
  main_stream_path?: string;
  sub_stream_path?: string;
  status?: string;
  state?: string;
  is_online?: boolean;
  location?: string;
  [key: string]: any;
}

export interface RecordingStatusItem {
  camera_serial: string;
  mode: string;
  /** Phase 10: true only when a recent segment exists (not just the policy). */
  last_segment_at?: string | null;
  recording_detail?: string | null;
  is_recording?: boolean;
  [key: string]: any;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: true,
      },
    },
  });
}

export const queryClient = createQueryClient();

export function useAuthStatus() {
  return useQuery<AuthStatus>({
    queryKey: ["authStatus"],
    queryFn: () => apiFetch<AuthStatus>("/api/v1/auth/status"),
    staleTime: 0,
  });
}

export function useCurrentUser(): AuthUser | null {
  const { data } = useAuthStatus();
  return data?.user ?? null;
}

export function useCameras() {
  return useQuery<CameraInfo[]>({
    queryKey: ["cameras"],
    queryFn: () => apiFetch<CameraInfo[]>("/api/v1/cameras"),
    staleTime: 30000,
  });
}

export interface AlertData {
  id: string;
  severity: "warning" | "critical";
  message: string;
  camera_serial?: string;
  timestamp?: string;
  acknowledged?: boolean;
  [key: string]: any;
}

export function useRecordingStatus() {
  return useQuery<RecordingStatusItem[]>({
    queryKey: ["recordingStatus"],
    queryFn: () => apiFetch<RecordingStatusItem[]>("/api/v1/recording/status"),
    refetchInterval: 10000,
    placeholderData: (previousData) => previousData,
  });
}

export function useAlerts() {
  return useQuery<AlertData[]>({
    queryKey: ["alerts"],
    queryFn: () => apiFetch<AlertData[]>("/api/v1/health/alerts"),
    refetchInterval: 10000,
    placeholderData: (previousData) => previousData,
  });
}

export interface HealthStatus {
  status: string;
  db_ok: boolean;
  mediamtx_ok: boolean;
  storage_ok: boolean;
  total_cameras: number;
  active_cameras: number;
  details?: Record<string, any>;
}

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthStatus>("/api/v1/health"),
    refetchInterval: 10000,
    placeholderData: (previousData) => previousData,
  });
}

export interface EventsResponse {
  items: Array<{ id: number; [key: string]: any }>;
  total: number;
}

export function useUnreadCount() {
  const readEventIds = useUiStore((s) => s.readEventIds);
  const query = useQuery<EventsResponse>({
    queryKey: ["recentEvents50"],
    queryFn: () => apiFetch<EventsResponse>("/api/v1/events?limit=50"),
    refetchInterval: 10000,
    placeholderData: (previousData) => previousData,
  });

  const unreadCount = React.useMemo(() => {
    if (!query.data?.items) return 0;
    // Phase 10: shared review state wins; fall back to this browser's read marks for old servers.
    return query.data.items.filter((item) =>
      typeof item.review_state === "string" ? item.review_state === "new" : !readEventIds.has(item.id)
    ).length;
  }, [query.data?.items, readEventIds]);

  return { ...query, unreadCount };
}