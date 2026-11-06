import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface UserMe {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  cognito_sub?: string | null;
  permissions: string[];
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}

export function useMe() {
  return useQuery<UserMe>({
    queryKey: ["authMe"],
    queryFn: () => apiFetch<UserMe>("/api/v1/auth/me"),
    staleTime: 30000,
  });
}

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0, // T-09-45: do not retain passwords in query cache
    mutationFn: async (payload: PasswordChangePayload) => {
      return apiFetch("/api/v1/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["authStatus"] });
      queryClient.invalidateQueries({ queryKey: ["authMe"] });
    },
  });
}
