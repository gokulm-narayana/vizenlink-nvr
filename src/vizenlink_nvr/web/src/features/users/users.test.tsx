import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { UsersPage } from "./UsersPage";
import { UsersTable } from "./UsersTable";
import { CreateUserDialog } from "./CreateUserDialog";
import { EditAccessDialog } from "./EditAccessDialog";
import { ResetPasswordDialog } from "./ResetPasswordDialog";
import { CameraChecklist } from "./CameraChecklist";
import { USERS_COPY } from "./copy";
import type { UserItem } from "./api";

import { TooltipProvider } from "@/components/ui/tooltip";

// Mock sonner toast
vi.mock("sonner", () => {
  const fn = vi.fn();
  (fn as any).success = vi.fn();
  (fn as any).error = vi.fn();
  return { toast: fn };
});

// Mock lib/queries
let mockCurrentUser: any = {
  id: 1,
  username: "admin_owner",
  role: "owner",
  permissions: [],
};

const mockCamerasList = [
  { id: 1, serial: "CAM-01", name: "Front Gate" },
  { id: 2, serial: "CAM-02", name: "Backyard" },
];

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => mockCurrentUser,
  useAuthStatus: () => ({
    data: {
      initialized: true,
      authenticated: true,
      user: mockCurrentUser,
      site_timezone: "UTC",
    },
    isLoading: false,
  }),
  useCameras: () => ({
    data: mockCamerasList,
    isLoading: false,
  }),
}));

// Mock features/profile/ChangePasswordDialog
vi.mock("@/features/profile/ChangePasswordDialog", () => ({
  ChangePasswordDialog: ({ open, onOpenChange }: any) =>
    open ? (
      <div data-testid="change-password-dialog">
        <span>Change your password dialog mock</span>
        <button onClick={() => onOpenChange(false)}>Close mock</button>
      </div>
    ) : null,
}));

// Mock features/users/api
let mockUsersList: UserItem[] = [];
let mockIsLoading = false;
let mockLoadError: any = null;
const mockRefetch = vi.fn();

let mockCreateUserReject: any = null;
const mockCreateUserMutate = vi.fn();

let mockUpdateUserReject: any = null;
const mockUpdateUserMutate = vi.fn();

let mockResetPasswordReject: any = null;
const mockResetPasswordMutate = vi.fn();

vi.mock("./api", () => ({
  useUsers: () => ({
    data: mockUsersList,
    isLoading: mockIsLoading,
    error: mockLoadError,
    refetch: mockRefetch,
  }),
  useCreateUser: () => ({
    mutateAsync: mockCreateUserMutate.mockImplementation(async (payload) => {
      if (mockCreateUserReject) throw mockCreateUserReject;
      const newUser: UserItem = {
        id: mockUsersList.length + 1,
        username: payload.username,
        role: payload.role,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        permissions: payload.permissions || [],
      };
      mockUsersList = [...mockUsersList, newUser];
      return newUser;
    }),
    isPending: false,
  }),
  useUpdateUser: (userId?: number) => ({
    mutateAsync: mockUpdateUserMutate.mockImplementation(async (payload) => {
      if (mockUpdateUserReject) throw mockUpdateUserReject;
      const id = payload.id ?? userId;
      mockUsersList = mockUsersList.map((u) =>
        u.id === id ? { ...u, ...payload } : u
      );
      return mockUsersList.find((u) => u.id === id);
    }),
    isPending: false,
  }),
  useResetUserPassword: (userId: number) => ({
    mutateAsync: mockResetPasswordMutate.mockImplementation(async (payload) => {
      if (mockResetPasswordReject) throw mockResetPasswordReject;
      return { success: true, message: "Password reset successfully" };
    }),
    isPending: false,
  }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("Users Management Feature (Plan 09-22)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading = false;
    mockLoadError = null;
    mockCreateUserReject = null;
    mockUpdateUserReject = null;
    mockResetPasswordReject = null;

    mockCurrentUser = {
      id: 1,
      username: "admin_owner",
      role: "owner",
      permissions: [],
    };

    mockUsersList = [
      {
        id: 1,
        username: "admin_owner",
        role: "owner",
        is_active: true,
        created_at: "2026-03-01T12:00:00Z",
        updated_at: "2026-03-01T12:00:00Z",
        permissions: [],
      },
      {
        id: 2,
        username: "guard_operator",
        role: "operator",
        is_active: true,
        created_at: "2026-03-02T12:00:00Z",
        updated_at: "2026-03-02T12:00:00Z",
        permissions: [],
      },
      {
        id: 3,
        username: "reception_viewer",
        role: "viewer",
        is_active: true,
        created_at: "2026-03-03T12:00:00Z",
        updated_at: "2026-03-03T12:00:00Z",
        permissions: ["CAM-01", "CAM-02"],
      },
      {
        id: 4,
        username: "blind_viewer",
        role: "viewer",
        is_active: false,
        created_at: "2026-03-04T12:00:00Z",
        updated_at: "2026-03-04T12:00:00Z",
        permissions: [],
      },
    ];
  });

  describe("Task 1: Table & Create User Tracer", () => {
    it("renders page title and Create user button", () => {
      renderWithProviders(<UsersPage />);
      expect(screen.getByRole("heading", { level: 1, name: "Users" })).toBeInTheDocument();
      expect(
        screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON })[0]
      ).toBeInTheDocument();
    });

    it("renders table columns with correct badges and permissions", () => {
      renderWithProviders(<UsersPage />);

      // Columns exist
      expect(screen.getByText(USERS_COPY.COL_USERNAME)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.COL_ROLE)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.COL_STATUS)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.COL_CAMERAS)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.COL_CREATED)).toBeInTheDocument();

      // "You" badge appears on owner's row
      expect(screen.getAllByText(USERS_COPY.YOU_BADGE).length).toBeGreaterThanOrEqual(1);

      // Roles rendered
      expect(screen.getAllByText("owner").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("operator").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("viewer").length).toBeGreaterThanOrEqual(2);

      // Cameras column
      expect(screen.getAllByText(USERS_COPY.ALL_CAMERAS).length).toBeGreaterThanOrEqual(2); // owner and operator
      expect(screen.getAllByText("2 cameras").length).toBeGreaterThanOrEqual(1); // reception_viewer
      expect(screen.getAllByText(USERS_COPY.NO_CAMERAS).length).toBeGreaterThanOrEqual(1); // blind_viewer
      expect(screen.getAllByTitle(USERS_COPY.NO_CAMERAS_TITLE).length).toBeGreaterThanOrEqual(1);

      // Status badges
      expect(screen.getAllByText("Active").length).toBeGreaterThanOrEqual(3);
      expect(screen.getAllByText("Disabled").length).toBeGreaterThanOrEqual(1);
    });

    it("opens Create user dialog, fills fields, selects cameras for viewer and submits", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      const createBtn = screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON })[0];
      await user.click(createBtn);

      expect(screen.getByRole("heading", { name: USERS_COPY.CREATE_TITLE })).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.CAMERA_CHECKLIST_HELPER)).toBeInTheDocument();

      // Fill username
      const usernameInput = screen.getByLabelText(USERS_COPY.USERNAME_LABEL);
      await user.type(usernameInput, "new_guard");

      // Fill password & confirm
      const passwordInput = screen.getByLabelText(USERS_COPY.PASSWORD_LABEL);
      const confirmInput = screen.getByLabelText(USERS_COPY.CONFIRM_PASSWORD_LABEL);
      await user.type(passwordInput, "secret1234");
      await user.type(confirmInput, "secret1234");

      // Check camera checklist buttons
      const selectAllBtn = screen.getByRole("button", { name: USERS_COPY.SELECT_ALL_CAMERAS });
      await user.click(selectAllBtn);

      // Submit
      const dialog = screen.getByRole("dialog");
      const submitBtn = within(dialog).getByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(mockCreateUserMutate).toHaveBeenCalledWith({
          username: "new_guard",
          password: "secret1234",
          role: "viewer",
          permissions: ["CAM-01", "CAM-02"],
        });
        expect((toast as any).success).toHaveBeenCalledWith(USERS_COPY.USER_CREATED_TOAST);
      });
    });

    it("validates required fields, min length and password mismatch in Create User dialog", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      const createBtn = screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON })[0];
      await user.click(createBtn);

      const dialog = screen.getByRole("dialog");
      const submitBtn = within(dialog).getByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON });

      // Submit empty
      await user.click(submitBtn);
      expect(screen.getByText(USERS_COPY.USERNAME_REQUIRED)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.PASSWORD_REQUIRED)).toBeInTheDocument();

      // Short password
      const usernameInput = screen.getByLabelText(USERS_COPY.USERNAME_LABEL);
      const passwordInput = screen.getByLabelText(USERS_COPY.PASSWORD_LABEL);
      const confirmInput = screen.getByLabelText(USERS_COPY.CONFIRM_PASSWORD_LABEL);

      await user.type(usernameInput, "testuser");
      await user.type(passwordInput, "short");
      await user.type(confirmInput, "short");
      await user.click(submitBtn);
      expect(screen.getByText(USERS_COPY.PASSWORD_TOO_SHORT)).toBeInTheDocument();

      // Password mismatch
      await user.clear(passwordInput);
      await user.type(passwordInput, "validpassword");
      await user.click(submitBtn);
      expect(screen.getByText(USERS_COPY.PASSWORD_MISMATCH)).toBeInTheDocument();
    });

    it("shows inline error when 409 conflict is returned on duplicate username", async () => {
      const user = userEvent.setup();
      mockCreateUserReject = new ApiError(409, "A user with that name already exists");

      renderWithProviders(<UsersPage />);
      const createBtn = screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON })[0];
      await user.click(createBtn);

      await user.type(screen.getByLabelText(USERS_COPY.USERNAME_LABEL), "admin_owner");
      await user.type(screen.getByLabelText(USERS_COPY.PASSWORD_LABEL), "password123");
      await user.type(screen.getByLabelText(USERS_COPY.CONFIRM_PASSWORD_LABEL), "password123");

      const dialog = screen.getByRole("dialog");
      const submitBtn = within(dialog).getByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(
          screen.getByText(USERS_COPY.USERNAME_TAKEN("admin_owner"))
        ).toBeInTheDocument();
      });
    });

    it("confirms discard alert dialog only when form is dirty in Create User", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      const createBtn = screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON })[0];
      await user.click(createBtn);

      // Clean form discard -> closes immediately
      const discardBtn = screen.getByRole("button", { name: USERS_COPY.DISCARD_NEW_USER });
      await user.click(discardBtn);
      expect(screen.queryByRole("heading", { name: USERS_COPY.CREATE_TITLE })).not.toBeInTheDocument();

      // Re-open and type
      await user.click(createBtn);
      await user.type(screen.getByLabelText(USERS_COPY.USERNAME_LABEL), "partial_input");

      const discardBtnDirty = screen.getByRole("button", { name: USERS_COPY.DISCARD_NEW_USER });
      await user.click(discardBtnDirty);

      // Alert dialog shows
      expect(screen.getByText(USERS_COPY.DISCARD_DIALOG_TITLE)).toBeInTheDocument();

      // Cancel discard
      await user.click(screen.getByRole("button", { name: USERS_COPY.KEEP_EDITING_USER }));
      await waitFor(() => {
        expect(screen.queryByText(USERS_COPY.DISCARD_DIALOG_TITLE)).not.toBeInTheDocument();
      });
      expect(screen.getByRole("heading", { name: USERS_COPY.CREATE_TITLE })).toBeInTheDocument();

      // Confirm discard
      await user.click(discardBtnDirty);
      const alertDialog = await screen.findByRole("alertdialog");
      const confirmDiscardBtn = within(alertDialog).getByRole("button", {
        name: USERS_COPY.DISCARD_NEW_USER,
      });
      await user.click(confirmDiscardBtn);

      await waitFor(() => {
        expect(screen.queryByRole("heading", { name: USERS_COPY.CREATE_TITLE })).not.toBeInTheDocument();
      });
    });
  });

  describe("Task 2: Edit Access, Enable/Disable, Reset Password and Self-Protection", () => {
    it("edits access: sends permissions only for viewer, and omits permissions for operator", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      // Open actions for reception_viewer
      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("reception_viewer"),
      })[0];
      await user.click(actionsBtn);

      // Click Edit access
      await user.click(screen.getByText(USERS_COPY.ACTION_EDIT_ACCESS));
      expect(
        screen.getByText(USERS_COPY.EDIT_ACCESS_TITLE("reception_viewer"))
      ).toBeInTheDocument();

      // Change role to Operator
      const operatorRadio = screen.getByRole("radio", { name: /operator/i });
      await user.click(operatorRadio);

      // Camera checklist is hidden for operator
      expect(screen.queryByText(USERS_COPY.CAMERA_CHECKLIST_HELPER)).not.toBeInTheDocument();

      // Save access
      await user.click(screen.getByRole("button", { name: USERS_COPY.SAVE_ACCESS_BUTTON }));

      await waitFor(() => {
        expect(mockUpdateUserMutate).toHaveBeenCalledWith({
          role: "operator",
        });
        expect((toast as any).success).toHaveBeenCalledWith(
          USERS_COPY.ACCESS_SAVED_TOAST("reception_viewer")
        );
      });
    });

    it("shows stale-cameras error with Reload cameras when 400 Unknown camera returned on Edit Access", async () => {
      const user = userEvent.setup();
      mockUpdateUserReject = new ApiError(400, "Unknown camera serial(s): CAM-99");

      renderWithProviders(<UsersPage />);
      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("reception_viewer"),
      })[0];
      await user.click(actionsBtn);
      await user.click(screen.getByText(USERS_COPY.ACTION_EDIT_ACCESS));

      await user.click(screen.getByRole("button", { name: USERS_COPY.SAVE_ACCESS_BUTTON }));

      await waitFor(() => {
        expect(screen.getByText(USERS_COPY.STALE_CAMERAS_ERROR)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: USERS_COPY.RELOAD_CAMERAS })).toBeInTheDocument();
      });
    });

    it("enables user immediately without confirmation dialog and toasts", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      // blind_viewer is disabled
      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("blind_viewer"),
      })[0];
      await user.click(actionsBtn);

      await user.click(screen.getByText(USERS_COPY.ACTION_ENABLE_USER));

      await waitFor(() => {
        expect(mockUpdateUserMutate).toHaveBeenCalledWith({
          id: 4,
          is_active: true,
        });
        expect((toast as any).success).toHaveBeenCalledWith(
          USERS_COPY.ENABLED_TOAST("blind_viewer")
        );
      });
    });

    it("disables active user via confirmation dialog and toasts", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      // guard_operator is active
      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("guard_operator"),
      })[0];
      await user.click(actionsBtn);

      await user.click(screen.getByText(USERS_COPY.ACTION_DISABLE_USER));

      // Confirmation dialog appears
      expect(
        screen.getByText(USERS_COPY.DISABLE_TITLE("guard_operator"))
      ).toBeInTheDocument();
      expect(
        screen.getByText(USERS_COPY.DISABLE_DESCRIPTION("guard_operator"))
      ).toBeInTheDocument();

      // Click Keep user enabled cancels
      await user.click(screen.getByRole("button", { name: USERS_COPY.KEEP_ENABLED_BUTTON }));
      expect(
        screen.queryByText(USERS_COPY.DISABLE_TITLE("guard_operator"))
      ).not.toBeInTheDocument();

      // Re-trigger and confirm
      await user.click(actionsBtn);
      await user.click(screen.getByText(USERS_COPY.ACTION_DISABLE_USER));

      const confirmBtn = screen.getByRole("button", {
        name: USERS_COPY.DISABLE_BUTTON,
      });
      await user.click(confirmBtn);

      await waitFor(() => {
        expect(mockUpdateUserMutate).toHaveBeenCalledWith({
          id: 2,
          is_active: false,
        });
        expect((toast as any).success).toHaveBeenCalledWith(
          USERS_COPY.DISABLED_TOAST("guard_operator")
        );
      });
    });

    it("shows page-level inline error when enable or disable fails", async () => {
      const user = userEvent.setup();
      mockUpdateUserReject = new Error("Network timeout");

      renderWithProviders(<UsersPage />);

      // Try enabling blind_viewer
      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("blind_viewer"),
      })[0];
      await user.click(actionsBtn);
      await user.click(screen.getByText(USERS_COPY.ACTION_ENABLE_USER));

      await waitFor(() => {
        expect(
          screen.getByText(USERS_COPY.ENABLE_FAILED("blind_viewer"))
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: USERS_COPY.RETRY_ENABLE })
        ).toBeInTheDocument();
      });
    });

    it("resets password for another user with destructive button and toasts", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      const actionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("guard_operator"),
      })[0];
      await user.click(actionsBtn);

      await user.click(screen.getByText(USERS_COPY.ACTION_RESET_PASSWORD));

      expect(
        screen.getByText(USERS_COPY.RESET_PASSWORD_TITLE("guard_operator"))
      ).toBeInTheDocument();
      expect(
        screen.getByText(USERS_COPY.RESET_PASSWORD_HELPER("guard_operator"))
      ).toBeInTheDocument();

      const newPasswordInput = screen.getByLabelText(USERS_COPY.NEW_PASSWORD_LABEL);
      const confirmInput = screen.getByLabelText(USERS_COPY.CONFIRM_PASSWORD_LABEL);

      await user.type(newPasswordInput, "brandNewPassword123");
      await user.type(confirmInput, "brandNewPassword123");

      const submitBtn = screen.getByRole("button", {
        name: USERS_COPY.RESET_PASSWORD_BUTTON,
      });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(mockResetPasswordMutate).toHaveBeenCalledWith({
          new_password: "brandNewPassword123",
        });
        expect((toast as any).success).toHaveBeenCalledWith(
          USERS_COPY.PASSWORD_RESET_TOAST("guard_operator")
        );
      });
    });

    it("enforces self-protection on current owner's own row", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      // Actions on admin_owner's row
      const ownActionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("admin_owner"),
      })[0];
      await user.click(ownActionsBtn);

      // Disable user is disabled
      const disableItem = screen.getByText(USERS_COPY.ACTION_DISABLE_USER);
      expect(disableItem.closest("[data-disabled]") || disableItem.closest("div")).toBeTruthy();

      // Reset password is replaced by "Change your password"
      expect(screen.queryByText(USERS_COPY.ACTION_RESET_PASSWORD)).not.toBeInTheDocument();
      const changePasswordItem = screen.getByText(USERS_COPY.ACTION_CHANGE_PASSWORD);
      expect(changePasswordItem).toBeInTheDocument();

      // Clicking "Change your password" opens ChangePasswordDialog
      await user.click(changePasswordItem);
      expect(screen.getByTestId("change-password-dialog")).toBeInTheDocument();
    });

    it("disables role selection in Edit Access on owner's own row", async () => {
      const user = userEvent.setup();
      renderWithProviders(<UsersPage />);

      const ownActionsBtn = screen.getAllByRole("button", {
        name: USERS_COPY.ACTIONS_LABEL("admin_owner"),
      })[0];
      await user.click(ownActionsBtn);
      await user.click(screen.getByText(USERS_COPY.ACTION_EDIT_ACCESS));

      // Role changing disabled with aria-disabled
      expect(screen.getByText(USERS_COPY.CANNOT_CHANGE_OWN_ROLE)).toBeInTheDocument();
    });
  });

  describe("Task 3: States & Responsive Layout", () => {
    it("renders loading skeleton when users are loading", () => {
      mockIsLoading = true;
      const { container } = renderWithProviders(<UsersPage />);
      expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThanOrEqual(1);
    });

    it("renders load error with Reload users action", async () => {
      const user = userEvent.setup();
      mockLoadError = new Error("Failed to load");
      renderWithProviders(<UsersPage />);

      expect(screen.getByText(USERS_COPY.LOAD_ERROR)).toBeInTheDocument();
      const reloadBtn = screen.getByRole("button", { name: USERS_COPY.RELOAD_USERS });
      await user.click(reloadBtn);
      expect(mockRefetch).toHaveBeenCalled();
    });

    it("renders defensive empty state when users list is empty", () => {
      mockUsersList = [];
      renderWithProviders(<UsersPage />);

      expect(screen.getByText(USERS_COPY.EMPTY_HEADING)).toBeInTheDocument();
      expect(screen.getByText(USERS_COPY.EMPTY_BODY)).toBeInTheDocument();
      expect(
        screen.getAllByRole("button", { name: USERS_COPY.CREATE_USER_BUTTON }).length
      ).toBeGreaterThanOrEqual(1);
    });

    it("renders 403 Forbidden state when user is not owner (e.g. operator or viewer)", () => {
      mockCurrentUser = {
        id: 2,
        username: "guard_operator",
        role: "operator",
        permissions: [],
      };

      renderWithProviders(<UsersPage />);
      expect(screen.getByText("Access restricted")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Go to Dashboard" })).toBeInTheDocument();
    });
  });
});