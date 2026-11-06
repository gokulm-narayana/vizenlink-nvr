import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { ChangePasswordDialog } from "./ChangePasswordDialog";
import { ProfilePage } from "./ProfilePage";
import { UserMenu } from "@/components/shell/UserMenu";
import { useUiStore } from "@/stores/ui";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

let mockCurrentUser: any = null;
let mockMeData: any = null;
let mockChangePasswordReject: any = null;
const mockSignOut = vi.fn();

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => mockCurrentUser,
  useCameras: () => ({
    data: [
      { id: 1, serial: "CAM-01", name: "Front Door" },
      { id: 2, serial: "CAM-02", name: "Back Yard" },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/features/auth/api", () => ({
  useSignOut: () => mockSignOut,
}));

vi.mock("./api", () => ({
  useMe: () => ({
    data: mockMeData,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useChangePassword: () => ({
    mutateAsync: vi.fn().mockImplementation(async (payload) => {
      if (mockChangePasswordReject) {
        throw mockChangePasswordReject;
      }
      return { success: true };
    }),
    isPending: false,
  }),
}));

describe("Profile & Change Password Feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChangePasswordReject = null;
    useUiStore.setState({ theme: "dark", viewMode: "advanced" });

    mockCurrentUser = {
      id: 1,
      username: "alice",
      role: "operator",
      permissions: ["*"],
    };

    mockMeData = {
      id: 1,
      username: "alice",
      role: "operator",
      is_active: true,
      permissions: ["*"],
    };
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("ChangePasswordDialog", () => {
    it("validates password length and match without calling API", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <ChangePasswordDialog open={true} onOpenChange={vi.fn()} />
      );

      const currentInput = screen.getByLabelText("Current password");
      const newInput = screen.getByLabelText("New password");
      const confirmInput = screen.getByLabelText("Confirm new password");
      const submitBtn = screen.getByRole("button", { name: "Change password" });

      await user.type(currentInput, "oldpass123");
      await user.type(newInput, "short");
      await user.type(confirmInput, "short");
      await user.click(submitBtn);

      // Should show too short error
      expect(
        screen.getByText("New password must be at least 8 characters. Use a longer password and try again.")
      ).toBeInTheDocument();

      // Fix length but mismatch confirm
      await user.clear(newInput);
      await user.type(newInput, "ValidPassword123");
      await user.clear(confirmInput);
      await user.type(confirmInput, "DifferentPass123");
      await user.click(submitBtn);

      expect(
        screen.getByText("Passwords don't match. Re-enter both and try again.")
      ).toBeInTheDocument();
    });

    it("submits valid passwords and shows success toast on 200", async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      renderWithProviders(
        <ChangePasswordDialog open={true} onOpenChange={onOpenChange} />
      );

      await user.type(screen.getByLabelText("Current password"), "CurrentPass123");
      await user.type(screen.getByLabelText("New password"), "NewSecurePass123");
      await user.type(screen.getByLabelText("Confirm new password"), "NewSecurePass123");

      await user.click(screen.getByRole("button", { name: "Change password" }));

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith("Password changed. Your other devices were signed out.");
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it("shows specific error and focuses current password on 400 wrong password", async () => {
      mockChangePasswordReject = new ApiError(400, "Current password is incorrect");
      const user = userEvent.setup();
      renderWithProviders(
        <ChangePasswordDialog open={true} onOpenChange={vi.fn()} />
      );

      const currentInput = screen.getByLabelText("Current password");
      await user.type(currentInput, "WrongPass123");
      await user.type(screen.getByLabelText("New password"), "NewSecurePass123");
      await user.type(screen.getByLabelText("Confirm new password"), "NewSecurePass123");

      await user.click(screen.getByRole("button", { name: "Change password" }));

      await waitFor(() => {
        expect(
          screen.getByText("Current password is incorrect. Check it and try again.")
        ).toBeInTheDocument();
      });

      expect(currentInput).toHaveFocus();
    });

    it("shows general error alert on network / server failure", async () => {
      mockChangePasswordReject = new Error("Network error");
      const user = userEvent.setup();
      renderWithProviders(
        <ChangePasswordDialog open={true} onOpenChange={vi.fn()} />
      );

      await user.type(screen.getByLabelText("Current password"), "Pass12345");
      await user.type(screen.getByLabelText("New password"), "NewPass12345");
      await user.type(screen.getByLabelText("Confirm new password"), "NewPass12345");

      await user.click(screen.getByRole("button", { name: "Change password" }));

      await waitFor(() => {
        expect(
          screen.getByText("Couldn't change your password. Check your connection and try again.")
        ).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: "Retry change password" })).toBeInTheDocument();
    });
  });

  describe("UserMenu Integration", () => {
    it("renders Change password item and opens dialog when clicked", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UserMenu />);

      const trigger = screen.getByRole("button", { name: /Account menu/i });
      await user.click(trigger);

      const changePwItem = screen.getByRole("menuitem", { name: "Change password" });
      expect(changePwItem).toBeInTheDocument();

      await user.click(changePwItem);

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Change password" })).toBeInTheDocument();
    });
  });

  describe("ProfilePage", () => {
    it("renders Account, Security, and Preferences cards for operator", () => {
      renderWithProviders(<ProfilePage />);

      // Account card
      expect(screen.getByText("alice")).toBeInTheDocument();
      expect(screen.getByText("operator")).toBeInTheDocument();
      expect(
        screen.getByText("Watches every camera, saves snapshots and clips, adds and edits cameras.")
      ).toBeInTheDocument();
      expect(screen.getByText("All cameras")).toBeInTheDocument();

      // Security card
      expect(screen.getByRole("button", { name: "Change password" })).toBeInTheDocument();

      // Preferences card
      expect(screen.getByText("Light")).toBeInTheDocument();
      expect(screen.getByText("Dark")).toBeInTheDocument();
      expect(screen.getByText("System")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    });

    it("renders viewer camera list or empty copy when viewer has restricted permissions", () => {
      mockMeData = {
        id: 3,
        username: "guard",
        role: "viewer",
        is_active: true,
        permissions: ["CAM-01"],
      };

      const { rerender } = renderWithProviders(<ProfilePage />);
      expect(screen.getByText("Front Door")).toBeInTheDocument();

      // Viewer with no cameras
      mockMeData = {
        id: 4,
        username: "noviewer",
        role: "viewer",
        is_active: true,
        permissions: [],
      };

      rerender(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter>
            <ProfilePage />
          </MemoryRouter>
        </QueryClientProvider>
      );

      expect(
        screen.getByText("None yet. Ask the NVR owner to give you access to a camera.")
      ).toBeInTheDocument();
    });

    it("changes theme and view mode from preferences card", async () => {
      const user = userEvent.setup();
      renderWithProviders(<ProfilePage />);

      // Click Light theme
      const lightLabel = screen.getByText("Light");
      await user.click(lightLabel);
      expect(useUiStore.getState().theme).toBe("light");

      // Click Simple view mode
      const simpleBtn = screen.getByRole("radio", { name: "Simple" });
      await user.click(simpleBtn);
      expect(useUiStore.getState().viewMode).toBe("simple");

      // Click Sign out
      const signOutBtn = screen.getByRole("button", { name: "Sign out" });
      await user.click(signOutBtn);
      expect(mockSignOut).toHaveBeenCalled();
    });
  });
});
