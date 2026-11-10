import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
export type ViewMode = "simple" | "advanced";

export interface UiState {
  theme: Theme;
  sidebarOpen: boolean;
  viewMode: ViewMode;
  readEventIds: Set<number>;
  dismissedAlertIds: Set<string>;
  setTheme: (theme: Theme) => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setViewMode: (mode: ViewMode) => void;
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

function getInitialTheme(): Theme {
  try {
    const val = localStorage.getItem("nvr_theme");
    if (val === "light" || val === "dark" || val === "system") {
      return val;
    }
  } catch {
    // fallback
  }
  return "light"; // Phase 10: old VMS defaulted to the light theme
}

function getInitialSidebarOpen(): boolean {
  try {
    const val = localStorage.getItem("nvr_sidebar");
    if (val === "collapsed") {
      return false;
    }
  } catch {
    // fallback
  }
  return true; // absent means expanded (D-07)
}

function getInitialViewMode(): ViewMode {
  try {
    const val = localStorage.getItem("nvr_view_mode");
    if (val === "advanced") {
      return "advanced";
    }
  } catch {
    // fallback
  }
  return "simple";
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
  theme: getInitialTheme(),
  sidebarOpen: getInitialSidebarOpen(),
  viewMode: getInitialViewMode(),
  readEventIds: getInitialReadEvents(),
  dismissedAlertIds: new Set<string>(),

  setTheme: (theme: Theme) => {
    try {
      localStorage.setItem("nvr_theme", theme);
    } catch {
      // ignore storage errors
    }
    set({ theme });
  },

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

  setViewMode: (viewMode: ViewMode) => {
    try {
      localStorage.setItem("nvr_view_mode", viewMode);
    } catch {
      // ignore storage errors
    }
    set({ viewMode });
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
