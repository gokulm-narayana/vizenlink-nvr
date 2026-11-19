import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface PairedDevice {
  id: string;
  device_id: string;
  device_name: string;
  platform: string;
  user_id: number;
  username?: string;
  paired_at: string;
  last_seen_at: string;
  is_revoked: boolean;
  revoked_at?: string;
}

export interface QRInitResponse {
  pairing_code: string;
  qr_payload: string;
  expires_at: string;
  server_url?: string | null;
}

export function useQrInit() {
  return useMutation({
    gcTime: 0, // T-09-38: do not retain short-lived pairing secret in client cache
    mutationFn: async () => {
      return apiFetch<QRInitResponse>("/api/v1/mobile/qr/init", {
        method: "POST",
      });
    },
  });
}

export function useDevices() {
  return useQuery<PairedDevice[]>({
    queryKey: ["devices"],
    queryFn: () => apiFetch<PairedDevice[]>("/api/v1/mobile/devices"),
    staleTime: 10000,
  });
}

export function useRevokeDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (deviceId: string) => {
      return apiFetch(`/api/v1/mobile/devices/${deviceId}/revoke`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
    },
  });
}
