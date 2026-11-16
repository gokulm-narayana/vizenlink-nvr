import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
export type ViewMode = "simple" | "advanced";

export interface UiState {
  theme: Theme;
  sidebarOpen: boolean;
  viewMode: ViewMode;
  readEventIds: Set<number>;
  dismissedAlertIds: Set<string>;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  markEventRead: (id: number) => void;
  dismissAlert: (id: string) => void;
}

export function resolvedTheme(theme: Theme): "light" | "dark" {
  if (theme === "dark") return "dark";
  if (theme === "light") return "light";
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

function getInitialSidebarOpen(): boolean {
  try {
    const val = localStorage.getItem("nvr_sidebar");
    if (val === "collapsed") {
      return false;
    }
    if (val) return true;
  } catch {
    // fallback
  }
  // No saved choice: full sidebar on wide screens, icon rail on tablets / small laptops (Phase 10).
  if (typeof window !== "undefined" && typeof window.innerWidth === "number" && window.innerWidth > 0) {
    return window.innerWidth >= 1024;
  }
  return true;
}

function getInitialReadEvents(): Set<number> {
  try {
    const val = localStorage.getItem("nvr_read_events");
    if (val) {
      const parsed = JSON.parse(val);
      if (Array.isArray(parsed)) {
        return new Set(parsed.filter((n): n is number => typeof n === "number"));
      }
    }
  } catch {
    // fallback
  }
  return new Set();
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: "light",
  sidebarOpen: getInitialSidebarOpen(),
  viewMode: "simple",
  readEventIds: getInitialReadEvents(),
  dismissedAlertIds: new Set<string>(),

  setSidebarOpen: (open: boolean) => {
    try {
      localStorage.setItem("nvr_sidebar", open ? "expanded" : "collapsed");
    } catch {
      // ignore storage errors
    }
    set({ sidebarOpen: open });
  },

  toggleSidebar: () => {
    const next = !get().sidebarOpen;
    get().setSidebarOpen(next);
  },

  markEventRead: (id: number) => {
    const current = get().readEventIds;
    if (current.has(id)) return;
    const next = new Set(current);
    next.add(id);
    try {
      localStorage.setItem("nvr_read_events", JSON.stringify(Array.from(next)));
    } catch {
      // ignore
    }
    set({ readEventIds: next });
  },

  dismissAlert: (id: string) => {
    const next = new Set(get().dismissedAlertIds);
    next.add(id);
    set({ dismissedAlertIds: next });
  },
}));
