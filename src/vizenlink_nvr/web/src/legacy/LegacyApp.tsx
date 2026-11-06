import React, { useEffect, useState } from "react";
import { useCurrentUser } from "@/lib/queries";
import { useSignOut } from "@/features/auth/api";
import { LiveGrid, CameraInfo } from "./LiveGrid";
import { Header, ViewMode, ViewTab } from "./Header";
import { AlertsBanner, AlertData } from "./AlertsBanner";
import { Dashboard } from "./Dashboard";
import { EventFeed } from "./EventFeed";
import { PlaybackView } from "./PlaybackView";
import { GalleryView } from "./GalleryView";
import { CameraSettingsView } from "./CameraSettingsView";
import { PairedDevicesView } from "./PairedDevicesView";

type AppTab = ViewTab | "settings" | "devices";

export const LegacyApp: React.FC = () => {
  const currentUser = useCurrentUser();
  const signOut = useSignOut();

  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [recordingSerials, setRecordingSerials] = useState<Set<string>>(new Set());
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [currentTab, setCurrentTab] = useState<AppTab>("live");
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("nvr_view_mode") as ViewMode) || "simple";
  });
  const [readEventIds, setReadEventIds] = useState<Set<number>>(() => {
    try {
      const stored = localStorage.getItem("nvr_read_events");
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });
  const [unreadEventsCount, setUnreadEventsCount] = useState<number>(0);
  const [playbackJumpTarget, setPlaybackJumpTarget] = useState<{
    cameraSerial: string;
    timestamp: string;
  } | null>(null);

  const loadUnreadEvents = async () => {
    try {
      const res = await fetch("/api/v1/events?limit=50");
      if (res.ok) {
        const data = await res.json();
        const unread = data.items.filter((item: { id: number }) => !readEventIds.has(item.id)).length;
        setUnreadEventsCount(unread);
      }
    } catch {
      // Ignore background fetch failure
    }
  };

  const loadAlerts = async () => {
    try {
      const res = await fetch("/api/v1/health/alerts");
      if (res.ok) {
        const data = await res.json();
        setAlerts(data);
      }
    } catch {
      // Ignore background fetch failure
    }
  };

  const loadCamerasAndRecording = async () => {
    try {
      const [camsRes, recRes] = await Promise.all([
        fetch("/api/v1/cameras"),
        fetch("/api/v1/recording/status"),
      ]);

      if (camsRes.ok) {
        const cams = await camsRes.json();
        setCameras(cams);
      }

      if (recRes.ok) {
        const recList = await recRes.json();
        const activeRecs = new Set<string>();
        for (const item of recList) {
          if (item.mode === "continuous" || item.mode === "scheduled" || item.mode === "event") {
            activeRecs.add(item.camera_serial);
          }
        }
        setRecordingSerials(activeRecs);
      }
    } catch {
      // Ignore network errors on initial background load
    }
  };

  useEffect(() => {
    if (currentUser) {
      void loadCamerasAndRecording();
      void loadAlerts();
      void loadUnreadEvents();
    }
    const interval = setInterval(() => {
      if (currentUser) {
        void loadAlerts();
        void loadUnreadEvents();
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [currentUser, readEventIds]);

  const handleToggleViewMode = () => {
    const nextMode: ViewMode = viewMode === "simple" ? "advanced" : "simple";
    setViewMode(nextMode);
    localStorage.setItem("nvr_view_mode", nextMode);
  };

  const handleEventRead = (eventId: number) => {
    setReadEventIds((prev) => {
      if (prev.has(eventId)) return prev;
      const next = new Set(prev);
      next.add(eventId);
      localStorage.setItem("nvr_read_events", JSON.stringify(Array.from(next)));
      return next;
    });
    setUnreadEventsCount((prev) => Math.max(0, prev - 1));
  };

  const handleLogout = () => {
    void signOut();
  };

  const handleDismissAlert = (alertId: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== alertId));
  };

  const handleJumpToPlayback = (cameraSerial: string, timestamp: string) => {
    setPlaybackJumpTarget({ cameraSerial, timestamp });
    setCurrentTab("playback");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Navigation Header */}
      <Header
        currentTab={currentTab as ViewTab}
        onTabChange={setCurrentTab}
        viewMode={viewMode}
        onViewModeToggle={handleToggleViewMode}
        username={currentUser?.username}
        role={currentUser?.role}
        alertCount={alerts.length}
        unreadEventsCount={unreadEventsCount}
        onLogout={handleLogout}
      />

      {/* Sticky Operational Alerts Banner */}
      <AlertsBanner alerts={alerts} onDismiss={handleDismissAlert} />

      {/* Main View: Live Multiview Grid, Events Feed, or Dashboard */}
      <main style={{ flex: 1, overflow: "auto" }}>
        {currentTab === "live" && (
          <LiveGrid cameras={cameras} recordingSerials={recordingSerials} />
        )}
        {currentTab === "events" && (
          <EventFeed
            cameras={cameras}
            readEventIds={readEventIds}
            onEventRead={handleEventRead}
            onJumpToPlayback={handleJumpToPlayback}
          />
        )}
        {currentTab === "playback" && (
          <PlaybackView
            cameras={cameras}
            initialCameraSerial={playbackJumpTarget?.cameraSerial}
            initialTimestamp={playbackJumpTarget?.timestamp}
            onClearInitialJump={() => setPlaybackJumpTarget(null)}
            onOpenGallery={() => setCurrentTab("gallery")}
          />
        )}
        {currentTab === "gallery" && (
          <GalleryView
            cameras={cameras}
            userRole={currentUser?.role}
            onJumpToPlayback={handleJumpToPlayback}
          />
        )}
        {currentTab === "settings" && (
          <CameraSettingsView
            cameras={cameras}
            userRole={currentUser?.role}
          />
        )}
        {currentTab === "devices" && (
          <PairedDevicesView userRole={currentUser?.role} />
        )}
        {currentTab === "dashboard" && (
          <Dashboard viewMode={viewMode} recordingCount={recordingSerials.size} />
        )}
      </main>
    </div>
  );
};

export default LegacyApp;
