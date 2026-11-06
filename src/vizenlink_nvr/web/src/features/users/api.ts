import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface UserItem {
  id: number;
  username: string;
  role: "owner" | "operator" | "viewer";
  is_active: boolean;
  cognito_sub?: string | null;
  created_at: string;
  updated_at: string;
  permissions: string[];
}

export interface CreateUserPayload {
  username: string;
  password: string;
  role: string;
  permissions?: string[];
}

export interface UpdateUserPayload {
  role?: string;
  is_active?: boolean;
  permissions?: string[];
}

export interface ResetUserPasswordPayload {
  new_password: string;
}

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => apiFetch<UserItem[]>("/api/v1/users"),
    refetchOnWindowFocus: true,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0, // T-09-49: do not retain user passwords in query client memory
    mutationFn: async (payload: CreateUserPayload): Promise<UserItem> => {
      return apiFetch<UserItem>("/api/v1/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useUpdateUser(userId?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      payload: UpdateUserPayload & { id?: number }
    ): Promise<UserItem> => {
      const targetId = payload.id ?? userId;
      if (!targetId) throw new Error("User ID is required");
      const { id: _, ...body } = payload;
      return apiFetch<UserItem>(`/api/v1/users/${targetId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useResetUserPassword(userId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0, // T-09-49: do not retain user passwords in query client memory
    mutationFn: async (payload: ResetUserPasswordPayload) => {
      return apiFetch<{ success: boolean; message: string }>(
        `/api/v1/users/${userId}/reset-password`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
