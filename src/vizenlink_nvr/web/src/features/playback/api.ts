import { useQuery, useMutation, type UseMutationResult } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { zonedDayBounds } from "@/lib/time";
import { useRecordingStatus } from "@/lib/queries";
import type { TimelineSegment, TimelineOutage, TimelineEvent } from "@/lib/timeline";

export interface TimelineResponse {
  camera_serial: string;
  start_time: string;
  end_time: string;
  segments: TimelineSegment[];
  outages: TimelineOutage[];
  events: TimelineEvent[];
}

export interface CalendarDaysResponse {
  camera_serial: string;
  year: number;
  month: number;
  days: string[];
}

export interface SaveSnapshotPayload {
  camera_serial: string;
  image_base64: string;
  title?: string;
  captured_at?: string;
}

export interface ExportClipPayload {
  camera_serial: string;
  start_time: string;
  end_time: string;
  title?: string;
}

export interface ExportClipResponse {
  id: number;
  camera_serial: string;
  start_time: string;
  end_time: string;
  file_path: string;
  file_size_bytes: number;
  title?: string;
}

export function useTimeline(serial: string | undefined, day: string | undefined, zone: string) {
  return useQuery<TimelineResponse>({
    queryKey: ["playback", "timeline", serial, day, zone],
    queryFn: async () => {
      if (!serial || !day) {
        return {
          camera_serial: serial || "",
          start_time: "",
          end_time: "",
          segments: [],
          outages: [],
          events: [],
        };
      }
      const [start, end] = zonedDayBounds(day, zone);
      return apiFetch<TimelineResponse>(
        `/api/v1/playback/timeline?camera_serial=${encodeURIComponent(serial)}&start_time=${encodeURIComponent(start.toISOString())}&end_time=${encodeURIComponent(end.toISOString())}`
      );
    },
    enabled: Boolean(serial && day),
  });
}

export function useRecordedDays(serial: string | undefined, year: number, month: number) {
  return useQuery<string[]>({
    queryKey: ["playback", "days", serial, year, month],
    queryFn: async () => {
      if (!serial) return [];
      const res = await apiFetch<CalendarDaysResponse>(
        `/api/v1/playback/days?camera_serial=${encodeURIComponent(serial)}&year=${year}&month=${month}`
      );
      return res.days || [];
    },
    enabled: Boolean(serial),
  });
}

export function useCameraRetention(serial: string | undefined): number | null {
  const { data: statuses } = useRecordingStatus();
  if (!serial || !statuses) return null;
  const match = statuses.find((s) => s.camera_serial === serial);
  return match?.retention_days ?? null;
}

export function useSaveSnapshot(): UseMutationResult<unknown, Error, SaveSnapshotPayload> {
  return useMutation({
    mutationFn: (payload: SaveSnapshotPayload) =>
      apiFetch("/api/v1/playback/snapshot", {
        method: "POST",
        body: payload,
      }),
  });
}

export function useExportClip(): UseMutationResult<ExportClipResponse, Error, ExportClipPayload> {
  return useMutation({
    mutationFn: (payload: ExportClipPayload) =>
      apiFetch<ExportClipResponse>("/api/v1/playback/export", {
        method: "POST",
        body: payload,
      }),
  });
}
