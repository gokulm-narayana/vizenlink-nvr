import React from "react";

export interface AlertData {
  id: string;
  severity: string;
  title: string;
  message: string;
  timestamp: string;
  source: string;
}

interface AlertsBannerProps {
  alerts: AlertData[];
  onDismiss?: (id: string) => void;
}

export const AlertsBanner: React.FC<AlertsBannerProps> = ({ alerts, onDismiss }) => {
  if (alerts.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", padding: "8px 20px", background: "#0f172a" }}>
      {alerts.map((alert) => {
        const isCritical = alert.severity === "critical";
        return (
          <div
            key={alert.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "8px 12px",
              background: isCritical ? "#7f1d1d" : "#78350f",
              color: "#fff",
              borderRadius: "4px",
              borderLeft: `4px solid ${isCritical ? "#ef4444" : "#f59e0b"}`,
              fontSize: "13px",
            }}
          >
            <div>
              <strong>{alert.title}:</strong> {alert.message}
            </div>
            {onDismiss && (
              <button
                onClick={() => onDismiss(alert.id)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                ✕
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
};

