import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { apiFetch } from "@/lib/api";

export interface LoginVariables {
  username: string;
  password: string;
}

export interface SetupVariables {
  owner_username: string;
  owner_password: string;
  timezone: string;
  storage_path: string;
  allow_system_disk: boolean;
}

export function useLogin() {
  return useMutation({
    mutationFn: (variables: LoginVariables) =>
      apiFetch<{ user: any }>("/api/v1/auth/login", {
        method: "POST",
        body: variables,
      }),
    gcTime: 0,
  });
}

export function useSetup() {
  return useMutation({
    mutationFn: (variables: SetupVariables) =>
      apiFetch<{ user: any }>("/api/v1/auth/setup", {
        method: "POST",
        body: variables,
      }),
    gcTime: 0,
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () =>
      apiFetch<void>("/api/v1/auth/logout", {
        method: "POST",
      }),
    gcTime: 0,
  });
}

export function useSignOut() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return async () => {
    let ok = false;
    try {
      const res = await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      ok = res.ok;
    } catch {
      ok = false;
    } finally {
      queryClient.clear();
      void navigate("/login", {
        replace: true,
        state: { signOutFailed: !ok },
      });
    }
  };
}
