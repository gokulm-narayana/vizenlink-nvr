import { useQuery } from "@tanstack/react-query";

export interface StorageTelemetry {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  reserve_bytes: number;
}

export interface StorageStatusResponse {
  storage_path: string;
  allow_system_disk: boolean;
  reserve_bytes: number;
  health_state: string;
  health_reason?: string | null;
  telemetry?: StorageTelemetry | null;
  estimated_retention_days?: number | null;
}

export interface OutageRecord {
  id: number;
  camera_serial: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  reason: string | null;
}

export function useStorageStatus() {
  return useQuery<StorageStatusResponse, Error>({
    queryKey: ["storage", "status"],
    queryFn: async () => {
      const res = await fetch("/api/v1/storage/status");
      if (!res.ok) {
        throw new Error(`Failed to load storage status: HTTP ${res.status}`);
      }
      return (await res.json()) as StorageStatusResponse;
    },
    refetchInterval: 5000,
  });
}

export function useOutages() {
  return useQuery<OutageRecord[], Error>({
    queryKey: ["health", "outages"],
    queryFn: async () => {
      const res = await fetch("/api/v1/health/outages?limit=50");
      if (!res.ok) {
        throw new Error(`Failed to load outages: HTTP ${res.status}`);
      }
      return (await res.json()) as OutageRecord[];
    },
    refetchInterval: 10000,
  });
}
