import React from "react";

export type ViewTab = "live" | "dashboard" | "events" | "playback" | "gallery";
export type ViewMode = "simple" | "advanced";

interface HeaderProps {
  currentTab: ViewTab;
  onTabChange: (tab: ViewTab) => void;
  viewMode: ViewMode;
  onViewModeToggle: () => void;
  username?: string;
  role?: string;
  alertCount: number;
  unreadEventsCount?: number;
  onLogout: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onTabChange,
  viewMode,
  onViewModeToggle,
  username,
  role,
  alertCount,
  unreadEventsCount = 0,
  onLogout,
}) => {
  return (
    <header
      style={{
        height: "60px",
        background: "#1e293b",
        borderBottom: "1px solid #334155",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0 20px",
      }}
    >
      {/* Brand & Tabs */}
      <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
        <h1 style={{ fontSize: "18px", margin: 0, fontWeight: "bold", color: "#38bdf8" }}>
          VizenLink NVR
        </h1>

        <nav style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => onTabChange("live")}
            style={{
              background: currentTab === "live" ? "#0f172a" : "transparent",
              color: currentTab === "live" ? "#38bdf8" : "#94a3b8",
              border: "1px solid",
              borderColor: currentTab === "live" ? "#38bdf8" : "transparent",
              borderRadius: "4px",
              padding: "6px 12px",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Live Multiview
          </button>
          <button
            onClick={() => onTabChange("playback")}
            style={{
              background: currentTab === "playback" ? "#0f172a" : "transparent",
              color: currentTab === "playback" ? "#38bdf8" : "#94a3b8",
              border: "1px solid",
              borderColor: currentTab === "playback" ? "#38bdf8" : "transparent",
              borderRadius: "4px",
              padding: "6px 12px",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Playback
          </button>
          <button
            onClick={() => onTabChange("gallery")}
            style={{
              background: currentTab === "gallery" ? "#0f172a" : "transparent",
              color: currentTab === "gallery" ? "#38bdf8" : "#94a3b8",
              border: "1px solid",
              borderColor: currentTab === "gallery" ? "#38bdf8" : "transparent",
              borderRadius: "4px",
              padding: "6px 12px",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Gallery
          </button>
          <button
            onClick={() => onTabChange("events")}
            style={{
              background: currentTab === "events" ? "#0f172a" : "transparent",
              color: currentTab === "events" ? "#38bdf8" : "#94a3b8",
              border: "1px solid",
              borderColor: currentTab === "events" ? "#38bdf8" : "transparent",
              borderRadius: "4px",
              padding: "6px 12px",
              cursor: "pointer",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            Events
            {unreadEventsCount > 0 && (
              <span
                style={{
                  background: "#38bdf8",
                  color: "#0f172a",
                  borderRadius: "10px",
                  padding: "1px 6px",
                  fontSize: "11px",
                  fontWeight: "bold",
                }}
              >
                {unreadEventsCount}
              </span>
            )}
          </button>
          <button
            onClick={() => onTabChange("dashboard")}
            style={{
              background: currentTab === "dashboard" ? "#0f172a" : "transparent",
              color: currentTab === "dashboard" ? "#38bdf8" : "#94a3b8",
              border: "1px solid",
              borderColor: currentTab === "dashboard" ? "#38bdf8" : "transparent",
              borderRadius: "4px",
              padding: "6px 12px",
              cursor: "pointer",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            Dashboard
            {alertCount > 0 && (
              <span
                style={{
                  background: "#ef4444",
                  color: "#fff",
                  borderRadius: "10px",
                  padding: "1px 6px",
                  fontSize: "11px",
                }}
              >
                {alertCount}
              </span>
            )}
          </button>
        </nav>
      </div>

      {/* Right Controls: Simple/Advanced Toggle, User, Signout */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        {/* Simple vs Advanced Toggle (AUTH-06) */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#94a3b8" }}>
          <span>Mode:</span>
          <button
            onClick={onViewModeToggle}
            title="Toggle between Simple and Advanced UI modes"
            style={{
              background: viewMode === "advanced" ? "#4f46e5" : "#334155",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              padding: "4px 8px",
              cursor: "pointer",
              fontWeight: "bold",
              textTransform: "uppercase",
              fontSize: "11px",
            }}
          >
            {viewMode}
          </button>
        </div>

        {username && (
          <span style={{ fontSize: "13px", color: "#cbd5e1" }}>
            <strong>{username}</strong> <span style={{ color: "#94a3b8" }}>({role})</span>
          </span>
        )}

        <button
          onClick={onLogout}
          style={{
            background: "#ef4444",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            padding: "6px 12px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          Sign Out
        </button>
      </div>
    </header>
  );
};

