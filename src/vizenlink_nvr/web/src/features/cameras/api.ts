import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface CameraSettingsData {
  identity: {
    name: string;
    location: string;
    timezone?: string;
    supported_timezones: Array<{ code: string; label: string }>;
  };
  device_info: {
    manufacturer: string;
    model: string;
    firmware_version: string;
    serial_number: string;
    hardware_id: string;
  };
  encoders: Array<{
    profile_token: string;
    profile_name: string;
    venc_token: string;
    current: {
      encoding: string;
      width: number;
      height: number;
      quality: number;
      frame_rate_limit: number;
      bitrate_limit_kbps: number;
      gov_length: number;
      profile: string;
    };
    options: {
      encodings: string[];
      resolutions: Array<{ width: number; height: number }>;
      quality_range: [number, number];
      frame_rate_range: [number, number];
      bitrate_range_kbps: [number, number];
      gov_length_range: [number, number];
    };
  }>;
  imaging: {
    current: {
      brightness: number;
      contrast: number;
      color_saturation: number;
      sharpness: number;
      ir_cut_filter: string;
      wdr_mode: string;
      wdr_level: number;
      night_vision_type: string;
      mirror_flip: string;
      anti_flicker: string;
    };
    options: {
      brightness_range: [number, number];
      contrast_range: [number, number];
      color_saturation_range: [number, number];
      sharpness_range: [number, number];
      ir_cut_filter_modes: string[];
      wdr_supported: boolean;
      wdr_level_range: [number, number];
      night_vision_color_capable: boolean;
      night_vision_smart_capable: boolean;
    };
  };
  osd: Array<{
    token: string;
    video_source_token: string;
    osd_type: string;
    position: string;
    plain_text?: string;
    date_format: string;
    time_format: string;
  }>;
}

export interface CameraHealthData {
  serial: string;
  online: boolean;
  uptime_seconds?: number;
  reboot_reason?: string;
  clock_sync_status: string;
  firmware_version: string;
  last_seen?: string;
}

export function useCameraSettings(serial: string) {
  return useQuery<CameraSettingsData>({
    queryKey: ["cameraSettings", serial],
    queryFn: () => apiFetch<CameraSettingsData>(`/api/v1/cameras/${serial}/settings`),
    enabled: Boolean(serial),
    staleTime: 10000,
  });
}

export function useCameraHealth(serial: string) {
  return useQuery<CameraHealthData>({
    queryKey: ["cameraHealth", serial],
    queryFn: () => apiFetch<CameraHealthData>(`/api/v1/cameras/${serial}/health`),
    enabled: Boolean(serial),
    staleTime: 10000,
  });
}

export interface IdentityPayload {
  name?: string;
  location?: string;
  timezone?: string;
  password?: string;
}

export function useSaveIdentity(serial: string) {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0, // T-09-36: do not retain camera passwords in query client memory
    mutationFn: async (payload: IdentityPayload) => {
      return apiFetch(`/api/v1/cameras/${serial}/settings/identity`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
  });
}

export interface EncoderPayload {
  venc_token: string;
  encoding: string;
  width: number;
  height: number;
  frame_rate_limit: number;
  bitrate_limit_kbps: number;
  quality: number;
}

export function useSaveEncoder(serial: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: EncoderPayload) => {
      return apiFetch(`/api/v1/cameras/${serial}/settings/encoder`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
    },
  });
}

export interface ImagingPayload {
  brightness: number;
  contrast: number;
  color_saturation: number;
  sharpness: number;
  ir_cut_filter: string;
  wdr_mode: string;
  wdr_level: number;
  night_vision_type: string;
  mirror_flip: string;
  anti_flicker: string;
}

export function useSaveImaging(serial: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ImagingPayload) => {
      return apiFetch(`/api/v1/cameras/${serial}/settings/imaging`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
    },
  });
}

export interface OsdItemPayload {
  token: string;
  video_source_token: string;
  osd_type: "Plain" | "DateAndTime";
  position: string;
  plain_text?: string;
}

export function useSaveOsd(serial: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payloads: OsdItemPayload[]) => {
      for (const payload of payloads) {
        await apiFetch(`/api/v1/cameras/${serial}/settings/osd`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraSettings", serial] });
    },
  });
}

export function useReboot(serial: string) {
  return useMutation({
    mutationFn: async () => {
      return apiFetch(`/api/v1/cameras/${serial}/reboot`, {
        method: "POST",
      });
    },
  });
}

export function useFactoryReset(serial: string) {
  return useMutation({
    mutationFn: async (params: { mode: "Soft" | "Hard"; confirmation: string }) => {
      return apiFetch(`/api/v1/cameras/${serial}/factory-reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
    },
  });
}
