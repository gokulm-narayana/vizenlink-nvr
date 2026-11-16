import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCurrentUser } from "@/lib/queries";

export interface GalleryItem {
  id: number;
  camera_serial: string;
  item_type: "snapshot" | "manual_clip" | "export_clip" | string;
  title: string;
  file_path: string;
  file_size_bytes: number;
  duration_seconds?: number | null;
  captured_at: string;
  created_at: string;
  user_id?: number | null;
}

export interface GalleryListResponse {
  items: GalleryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface GalleryFilters {
  camera_serial?: string;
  item_type?: string;
  start_time?: string;
  end_time?: string;
}

export function useGallery(filters: GalleryFilters, pageSize = 50) {
  return useInfiniteQuery<GalleryListResponse, Error>({
    queryKey: ["gallery", filters, pageSize],
    queryFn: async ({ pageParam = 0 }) => {
      const params = new URLSearchParams();
      params.set("limit", pageSize.toString());
      params.set("offset", (pageParam as number).toString());

      if (filters.camera_serial) params.set("camera_serial", filters.camera_serial);
      if (filters.item_type) params.set("item_type", filters.item_type);
      if (filters.start_time) params.set("start_time", filters.start_time);
      if (filters.end_time) params.set("end_time", filters.end_time);

      const res = await fetch(`/api/v1/gallery?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`Failed to load gallery items: HTTP ${res.status}`);
      }
      return (await res.json()) as GalleryListResponse;
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
  });
}

export interface GalleryShareResponse {
  item_id: number;
  share_url: string;
  qr_payload: string;
  expires_at: string;
}

export function useShareGalleryItem() {
  return useMutation<GalleryShareResponse, Error, number>({
    mutationFn: async (id: number) => {
      const res = await fetch(`/api/v1/gallery/${id}/share`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to share gallery item: HTTP ${res.status}`);
      }
      return (await res.json()) as GalleryShareResponse;
    },
  });
}

export function useDeleteGalleryItem() {
  const queryClient = useQueryClient();
  return useMutation<{ status: string; id: number }, Error, number>({
    mutationFn: async (id: number) => {
      const res = await fetch(`/api/v1/gallery/${id}`, { method: "DELETE" });
      if (!res.ok) {
        throw new Error(`Failed to delete gallery item: HTTP ${res.status}`);
      }
      return (await res.json()) as { status: string; id: number };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
    },
  });
}

export interface UserSummary {
  id: number;
  username: string;
}

export function useUsersList() {
  const user = useCurrentUser();
  return useQuery<UserSummary[]>({
    queryKey: ["users", "list"],
    queryFn: async () => {
      const res = await fetch("/api/v1/users");
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : data.users || [];
    },
    enabled: user?.role === "owner",
  });
}
