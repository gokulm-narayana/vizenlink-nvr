import { QueryClient, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

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

export function useRecordingStatus() {
  return useQuery<RecordingStatusItem[]>({
    queryKey: ["recordingStatus"],
    queryFn: () => apiFetch<RecordingStatusItem[]>("/api/v1/recording/status"),
    refetchInterval: 10000,
    placeholderData: (previousData) => previousData,
  });
}
