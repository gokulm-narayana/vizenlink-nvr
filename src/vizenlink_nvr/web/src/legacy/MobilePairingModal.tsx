import React, { useEffect, useState } from "react";

interface MobilePairingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface QRInitData {
  pairing_code: string;
  qr_payload: string;
  expires_at: string;
}

export const MobilePairingModal: React.FC<MobilePairingModalProps> = ({ isOpen, onClose }) => {
  const [data, setData] = useState<QRInitData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number>(300);
  const [copied, setCopied] = useState(false);

  const fetchQRCode = async () => {
    setLoading(true);
    setError(null);
    setCopied(false);
    try {
      const res = await fetch("/api/v1/mobile/qr/init", { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to initialize pairing session: ${res.statusText}`);
      }
      const json: QRInitData = await res.json();
      setData(json);

      const expDate = new Date(json.expires_at).getTime();
      const now = Date.now();
      setSecondsRemaining(Math.max(0, Math.floor((expDate - now) / 1000)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load QR code");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchQRCode();
    } else {
      setData(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !data || secondsRemaining <= 0) return;
    const timer = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [isOpen, data, secondsRemaining]);

  if (!isOpen) return null;

  const formatCode = (code: string) => {
    return code.match(/.{1,4}/g)?.join("-") || code;
  };

  const handleCopy = () => {
    if (data?.pairing_code) {
      navigator.clipboard.writeText(data.pairing_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const minutes = Math.floor(secondsRemaining / 60);
  const seconds = secondsRemaining % 60;
  const isExpired = secondsRemaining <= 0;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "20px",
      }}
    >
      <div
        style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "8px",
          width: "100%",
          maxWidth: "480px",
          padding: "24px",
          color: "#f8fafc",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 style={{ margin: 0, fontSize: "18px", fontWeight: "bold", color: "#38bdf8" }}>
            Pair Mobile Device
          </h2>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              fontSize: "20px",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#94a3b8" }}>
            Generating secure pairing token...
          </div>
        ) : error ? (
          <div style={{ padding: "20px", textAlign: "center" }}>
            <div style={{ color: "#ef4444", marginBottom: "16px" }}>{error}</div>
            <button
              onClick={fetchQRCode}
              style={{
                background: "#38bdf8",
                color: "#0f172a",
                border: "none",
                borderRadius: "4px",
                padding: "8px 16px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        ) : data ? (
          <div>
            <div style={{ textAlign: "center", marginBottom: "16px" }}>
              {/* QR Code graphic container */}
              <div
                style={{
                  background: "#ffffff",
                  padding: "16px",
                  borderRadius: "8px",
                  display: "inline-block",
                  boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.2)",
                  opacity: isExpired ? 0.3 : 1,
                }}
              >
                <svg width="180" height="180" viewBox="0 0 100 100" fill="#0f172a">
                  {/* Visual QR pattern styling */}
                  <rect x="0" y="0" width="30" height="30" fill="#0f172a" />
                  <rect x="5" y="5" width="20" height="20" fill="#ffffff" />
                  <rect x="10" y="10" width="10" height="10" fill="#0f172a" />

                  <rect x="70" y="0" width="30" height="30" fill="#0f172a" />
                  <rect x="75" y="5" width="20" height="20" fill="#ffffff" />
                  <rect x="80" y="10" width="10" height="10" fill="#0f172a" />

                  <rect x="0" y="70" width="30" height="30" fill="#0f172a" />
                  <rect x="5" y="75" width="20" height="20" fill="#ffffff" />
                  <rect x="10" y="80" width="10" height="10" fill="#0f172a" />

                  <circle cx="50" cy="50" r="12" fill="#0284c7" />
                  <rect x="36" y="12" width="6" height="6" />
                  <rect x="52" y="12" width="6" height="6" />
                  <rect x="36" y="24" width="6" height="6" />
                  <rect x="12" y="44" width="6" height="6" />
                  <rect x="24" y="56" width="6" height="6" />
                  <rect x="44" y="72" width="6" height="6" />
                  <rect x="72" y="44" width="6" height="6" />
                  <rect x="84" y="60" width="6" height="6" />
                  <rect x="64" y="80" width="6" height="6" />
                  <rect x="80" y="76" width="8" height="8" />
                </svg>
              </div>

              {isExpired ? (
                <div style={{ marginTop: "12px", color: "#ef4444", fontWeight: 600 }}>
                  Pairing code expired.
                  <div style={{ marginTop: "8px" }}>
                    <button
                      onClick={fetchQRCode}
                      style={{
                        background: "#38bdf8",
                        color: "#0f172a",
                        border: "none",
                        borderRadius: "4px",
                        padding: "6px 14px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Generate New Code
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: "10px", fontSize: "13px", color: "#94a3b8" }}>
                  Code expires in:{" "}
                  <strong style={{ color: secondsRemaining < 60 ? "#f59e0b" : "#38bdf8" }}>
                    {minutes}:{seconds.toString().padStart(2, "0")}
                  </strong>
                </div>
              )}
            </div>

            {/* Monospace Pairing Code */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "12px",
                marginBottom: "16px",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>
                Manual Pairing Code
              </div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "16px",
                  fontWeight: "bold",
                  color: "#38bdf8",
                  letterSpacing: "1px",
                }}
              >
                {formatCode(data.pairing_code)}
              </div>
              <button
                onClick={handleCopy}
                style={{
                  marginTop: "8px",
                  background: copied ? "#22c55e" : "#334155",
                  color: "#f8fafc",
                  border: "none",
                  borderRadius: "4px",
                  padding: "4px 10px",
                  fontSize: "12px",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                {copied ? "✓ Copied to clipboard" : "Copy Code"}
              </button>
            </div>

            {/* Instructions */}
            <div style={{ fontSize: "13px", color: "#94a3b8", lineHeight: "1.5", marginBottom: "16px" }}>
              <strong>Instructions:</strong>
              <ol style={{ paddingLeft: "20px", margin: "6px 0 0 0" }}>
                <li>Open the VizenLink mobile app on your iPhone or Android.</li>
                <li>Tap <strong>Connect to NVR on LAN</strong>.</li>
                <li>Scan the QR code above or enter the 32-character pairing code.</li>
              </ol>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                onClick={onClose}
                style={{
                  background: "#475569",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  padding: "8px 16px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Done
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

