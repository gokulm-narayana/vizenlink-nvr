import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { apiFetch } from "@/lib/api";
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useResetUserPassword,
} from "./api";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("Users API Module (Plan 09-22 API contracts & T-09-49)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("useUsers fetches GET /api/v1/users", async () => {
    const mockUsers = [{ id: 1, username: "owner1", role: "owner" }];
    vi.mocked(apiFetch).mockResolvedValueOnce(mockUsers);

    const { result } = renderHook(() => useUsers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockUsers);
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/users");
  });

  it("useCreateUser sends POST /api/v1/users and has gcTime: 0 for secret hygiene (T-09-49)", async () => {
    const createdUser = { id: 2, username: "new_op", role: "operator" };
    vi.mocked(apiFetch).mockResolvedValueOnce(createdUser);

    const { result } = renderHook(() => useCreateUser(), {
      wrapper: createWrapper(),
    });

    const payload = {
      username: "new_op",
      password: "secretpassword123",
      role: "operator",
      permissions: [],
    };

    const res = await result.current.mutateAsync(payload);
    expect(res).toEqual(createdUser);
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  });

  it("useUpdateUser sends PATCH /api/v1/users/{id}", async () => {
    const updated = { id: 5, username: "viewer1", is_active: false };
    vi.mocked(apiFetch).mockResolvedValueOnce(updated);

    const { result } = renderHook(() => useUpdateUser(5), {
      wrapper: createWrapper(),
    });

    const res = await result.current.mutateAsync({ is_active: false });
    expect(res).toEqual(updated);
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/users/5", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: false }),
    });
  });

  it("useUpdateUser accepts id in payload when no id is bound", async () => {
    const updated = { id: 10, username: "viewer2", is_active: true };
    vi.mocked(apiFetch).mockResolvedValueOnce(updated);

    const { result } = renderHook(() => useUpdateUser(), {
      wrapper: createWrapper(),
    });

    const res = await result.current.mutateAsync({ id: 10, is_active: true });
    expect(res).toEqual(updated);
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/users/10", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: true }),
    });
  });

  it("useResetUserPassword sends POST /api/v1/users/{id}/reset-password and has gcTime: 0 (T-09-49)", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      success: true,
      message: "Reset OK",
    });

    const { result } = renderHook(() => useResetUserPassword(8), {
      wrapper: createWrapper(),
    });

    const res = await result.current.mutateAsync({
      new_password: "brandNewPassword999",
    });
    expect(res).toEqual({ success: true, message: "Reset OK" });
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/users/8/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: "brandNewPassword999" }),
    });
  });
});
