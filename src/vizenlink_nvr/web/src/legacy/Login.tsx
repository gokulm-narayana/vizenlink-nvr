import React, { useState } from "react";

interface LoginProps {
  onSuccess: (user: any) => void;
}

export const Login: React.FC<LoginProps> = ({ onSuccess }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lockoutSec, setLockoutSec] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLockoutSec(null);
    setLoading(true);

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (res.status === 429) {
        const data = await res.json();
        setError("Account locked due to consecutive failed attempts.");
        setLockoutSec(900);
        return;
      }

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Invalid credentials");
      }

      const data = await res.json();
      onSuccess(data.user);
    } catch (err: any) {
      setError(err?.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "400px", margin: "80px auto", padding: "24px", background: "#1e293b", borderRadius: "8px" }}>
      <h2>VizenLink NVR Sign In</h2>
      <p style={{ color: "#94a3b8" }}>Enter your credentials to access live camera multiview and settings.</p>

      {error && (
        <div style={{ color: "#ef4444", marginBottom: "16px", background: "#450a0a", padding: "8px", borderRadius: "4px" }}>
          {error}
          {lockoutSec && <div>Please wait 15 minutes before retrying.</div>}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Username</label>
          <input
            type="text"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", marginBottom: "4px" }}>Password</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#0f172a", color: "#f8fafc", border: "1px solid #334155", borderRadius: "4px" }}
          />
        </div>

        <button
          type="submit"
          disabled={loading || lockoutSec !== null}
          style={{ width: "100%", padding: "10px", background: "#2563eb", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
};

