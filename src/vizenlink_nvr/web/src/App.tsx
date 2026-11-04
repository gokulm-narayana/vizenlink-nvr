import React, { useEffect, useState } from "react";
import { SetupWizard } from "./components/SetupWizard";
import { Login } from "./components/Login";
import { LiveGrid, CameraInfo } from "./components/LiveGrid";

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
  const [loading, setLoading] = useState(true);

  const checkStatus = async () => {
    try {
      const res = await fetch("/api/v1/auth/status");
      const data = await res.json();
      setAuthStatus(data);
      if (data.authenticated) {
        await loadCamerasAndRecording();
      }
    } catch {
      setAuthStatus({ initialized: true, authenticated: false });
    } finally {
      setLoading(false);
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
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setAuthStatus((prev) => (prev ? { ...prev, authenticated: false } : null));
    }
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
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <h1 style={{ fontSize: "18px", margin: 0, fontWeight: "bold", color: "#38bdf8" }}>VizenLink NVR</h1>
          <span style={{ fontSize: "12px", background: "#0f172a", padding: "2px 8px", borderRadius: "4px", color: "#94a3b8" }}>
            Live Multiview
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <span style={{ fontSize: "13px", color: "#cbd5e1" }}>
            Signed in as <strong>{authStatus?.user?.username}</strong> ({authStatus?.user?.role})
          </span>
          <button
            onClick={handleLogout}
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

      {/* Main Live Multiview Grid */}
      <main style={{ flex: 1, overflow: "hidden" }}>
        <LiveGrid cameras={cameras} recordingSerials={recordingSerials} />
      </main>
    </div>
  );
};
export default App;
