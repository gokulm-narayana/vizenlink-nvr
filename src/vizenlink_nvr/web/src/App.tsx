import React, { useEffect, useState } from "react";
import { SetupWizard } from "./components/SetupWizard";
import { Login } from "./components/Login";
import { LiveGrid, CameraInfo } from "./components/LiveGrid";
import { Header, ViewMode, ViewTab } from "./components/Header";
import { AlertsBanner, AlertData } from "./components/AlertsBanner";
import { Dashboard } from "./components/Dashboard";

interface AuthStatus {
  initialized: boolean;
  authenticated: boolean;
  user?: {
    id: number;
    username: string;
    role: string;
    permissions: string[];
  };
}

export const App: React.FC = () => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [recordingSerials, setRecordingSerials] = useState<Set<string>>(new Set());
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [currentTab, setCurrentTab] = useState<ViewTab>("live");
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("nvr_view_mode") as ViewMode) || "simple";
  });
  const [loading, setLoading] = useState(true);

  const checkStatus = async () => {
    try {
      const res = await fetch("/api/v1/auth/status");
      const data = await res.json();
      setAuthStatus(data);
      if (data.authenticated) {
        await Promise.all([loadCamerasAndRecording(), loadAlerts()]);
      }
    } catch {
      setAuthStatus({ initialized: true, authenticated: false });
    } finally {
      setLoading(false);
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
    checkStatus();
    const interval = setInterval(() => {
      if (authStatus?.authenticated) {
        loadAlerts();
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [authStatus?.authenticated]);

  const handleToggleViewMode = () => {
    const nextMode: ViewMode = viewMode === "simple" ? "advanced" : "simple";
    setViewMode(nextMode);
    localStorage.setItem("nvr_view_mode", nextMode);
  };

  const handleLogout = async () => {
    try {
      await fetch("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setAuthStatus((prev) => (prev ? { ...prev, authenticated: false } : null));
    }
  };

  const handleDismissAlert = (alertId: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== alertId));
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        Loading VizenLink NVR...
      </div>
    );
  }

  if (authStatus && !authStatus.initialized) {
    return <SetupWizard onComplete={checkStatus} />;
  }

  if (authStatus && !authStatus.authenticated) {
    return <Login onSuccess={checkStatus} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Navigation Header */}
      <Header
        currentTab={currentTab}
        onTabChange={setCurrentTab}
        viewMode={viewMode}
        onViewModeToggle={handleToggleViewMode}
        username={authStatus?.user?.username}
        role={authStatus?.user?.role}
        alertCount={alerts.length}
        onLogout={handleLogout}
      />

      {/* Sticky Operational Alerts Banner */}
      <AlertsBanner alerts={alerts} onDismiss={handleDismissAlert} />

      {/* Main View: Live Multiview Grid or Dashboard */}
      <main style={{ flex: 1, overflow: "auto" }}>
        {currentTab === "live" ? (
          <LiveGrid cameras={cameras} recordingSerials={recordingSerials} />
        ) : (
          <Dashboard viewMode={viewMode} recordingCount={recordingSerials.size} />
        )}
      </main>
    </div>
  );
};
export default App;
