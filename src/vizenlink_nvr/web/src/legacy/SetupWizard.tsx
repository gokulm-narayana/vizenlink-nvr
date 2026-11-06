import React, { useState } from "react";

interface SetupWizardProps {
  onComplete: () => void;
}

export const SetupWizard: React.FC<SetupWizardProps> = ({ onComplete }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [storagePath, setStoragePath] = useState("/var/lib/vizenlink-nvr/recordings");
  const [allowSystemDisk, setAllowSystemDisk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner_username: username,
          owner_password: password,
          timezone,
          storage_path: storagePath,
          allow_system_disk: allowSystemDisk,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Setup initialization failed");
      }

      onComplete();
    } catch (err: any) {
      setError(err?.message || "An unexpected error occurred during setup");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: "480px", margin: "60px auto", padding: "24px", background: "#1e293b", borderRadius: "8px" }}>
      <h2>VizenLink NVR Setup Wizard</h2>
      <p style={{ color: "#94a3b8" }}>Initialize your network video recorder with owner credentials and storage volume.</p>
      {error && <div style={{ color: "#ef4444", marginBottom: "16px", background: "#450a0a", padding: "8px", borderRadius: "4px" }}>{error}</div>}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Owner Username</label>
          <input
            type="text"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Owner Password (min 8 chars)</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Confirm Password</label>
          <input
            type="password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Timezone</label>
          <input
            type="text"
            required
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Recording Storage Directory</label>
          <input
            type="text"
            required
            value={storagePath}
            onChange={(e) => setStoragePath(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <input
              type="checkbox"
              checked={allowSystemDisk}
              onChange={(e) => setAllowSystemDisk(e.target.checked)}
            />
            Allow recordings on system root partition (testing/dev)
          </label>
        </div>

        <button
          type="submit"
          disabled={submitting}
          style={{ width: "100%", padding: "10px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}
        >
          {submitting ? "Initializing..." : "Complete Setup"}
        </button>
      </form>
    </div>
  );
};

