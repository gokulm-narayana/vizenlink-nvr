import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { CameraCreateRequestPayload } from "./schema";
import type { CameraInfo } from "@/lib/queries";

export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0, // T-09-41: do not retain camera passwords in query client memory
    mutationFn: async (payload: CameraCreateRequestPayload): Promise<CameraInfo> => {
      return apiFetch<CameraInfo>("/api/v1/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
  });
}
