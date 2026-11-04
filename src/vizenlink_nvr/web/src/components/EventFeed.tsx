import React, { useEffect, useState } from "react";
import { EventCard, EventData } from "./EventCard";

interface CameraItem {
  serial: string;
  name: string;
}

interface EventFeedProps {
  cameras: CameraItem[];
  onEventRead?: (eventId: number) => void;
  readEventIds: Set<number>;
}

export const EventFeed: React.FC<EventFeedProps> = ({
  cameras,
  onEventRead,
  readEventIds,
}) => {
  const [events, setEvents] = useState<EventData[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedCamera, setSelectedCamera] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");
  const [lockedFilter, setLockedFilter] = useState<string>("");
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");

  const limit = 24;

  const fetchEvents = async (newOffset: number, append: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", limit.toString());
      params.set("offset", newOffset.toString());

      if (selectedCamera) params.set("camera_serial", selectedCamera);
      if (selectedType) params.set("event_type", selectedType);
      if (lockedFilter === "locked") params.set("is_locked", "true");
      if (lockedFilter === "unlocked") params.set("is_locked", "false");
      if (startTime) params.set("start_time", new Date(startTime).toISOString());
      if (endTime) params.set("end_time", new Date(endTime).toISOString());

      const res = await fetch(`/api/v1/events?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch events: HTTP ${res.status}`);
      }
      const data = await res.json();
      setEvents((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setOffset(newOffset);
    } catch (err: any) {
      setError(err.message || "Failed to load events");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents(0, false);
  }, [selectedCamera, selectedType, lockedFilter, startTime, endTime]);

  const handleLoadMore = () => {
    fetchEvents(offset + limit, true);
  };

  const handleLockToggle = async (eventId: number, newLocked: boolean) => {
    try {
      const endpoint = newLocked ? `/api/v1/events/${eventId}/lock` : `/api/v1/events/${eventId}/unlock`;
      const res = await fetch(endpoint, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to change lock state: HTTP ${res.status}`);
      }
      const updated: EventData = await res.json();
      setEvents((prev) =>
        prev.map((e) => (e.id === eventId ? { ...e, is_locked: updated.is_locked } : e))
      );
    } catch (err: any) {
      alert(`Error toggling event lock: ${err.message}`);
    }
  };

  const cameraMap = new Map<string, string>();
  for (const c of cameras) {
    cameraMap.set(c.serial, c.name);
  }

  return (
    <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header & Filter Controls */}
      <div
        style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "8px",
          padding: "16px",
          display: "flex",
          flexWrap: "wrap",
          gap: "16px",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center" }}>
          {/* Camera Filter */}
          <select
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "6px 10px",
              fontSize: "13px",
            }}
          >
            <option value="">All Cameras</option>
            {cameras.map((c) => (
              <option key={c.serial} value={c.serial}>
                {c.name || c.serial}
              </option>
            ))}
          </select>

          {/* Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "6px 10px",
              fontSize: "13px",
            }}
          >
            <option value="">All Event Types</option>
            <option value="motion">Motion</option>
            <option value="line_crossing">Line Crossing</option>
            <option value="tamper">Tamper</option>
            <option value="person">Person Detection</option>
            <option value="vehicle">Vehicle Detection</option>
          </select>

          {/* Lock Filter */}
          <select
            value={lockedFilter}
            onChange={(e) => setLockedFilter(e.target.value)}
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "6px 10px",
              fontSize: "13px",
            }}
          >
            <option value="">All Protection States</option>
            <option value="locked">Locked / Protected</option>
            <option value="unlocked">Unlocked</option>
          </select>

          {/* Start Time */}
          <input
            type="datetime-local"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            placeholder="From"
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "5px 8px",
              fontSize: "12px",
            }}
          />

          {/* End Time */}
          <input
            type="datetime-local"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            placeholder="To"
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #475569",
              borderRadius: "4px",
              padding: "5px 8px",
              fontSize: "12px",
            }}
          />

          {(selectedCamera || selectedType || lockedFilter || startTime || endTime) && (
            <button
              onClick={() => {
                setSelectedCamera("");
                setSelectedType("");
                setLockedFilter("");
                setStartTime("");
                setEndTime("");
              }}
              style={{
                background: "transparent",
                color: "#94a3b8",
                border: "none",
                cursor: "pointer",
                fontSize: "12px",
                textDecoration: "underline",
              }}
            >
              Reset Filters
            </button>
          )}
        </div>

        <div style={{ color: "#94a3b8", fontSize: "13px" }}>
          Total Events: <strong style={{ color: "#f8fafc" }}>{total}</strong>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div
          style={{
            background: "#fee2e2",
            color: "#b91c1c",
            padding: "12px",
            borderRadius: "6px",
            fontSize: "14px",
          }}
        >
          {error}
        </div>
      )}

      {/* Empty State */}
      {!loading && events.length === 0 && (
        <div
          style={{
            padding: "60px 20px",
            textAlign: "center",
            color: "#64748b",
            background: "#1e293b",
            borderRadius: "8px",
            border: "1px dashed #334155",
          }}
        >
          <div style={{ fontSize: "32px", marginBottom: "8px" }}>🔔</div>
          <div style={{ fontSize: "16px", fontWeight: 600, color: "#94a3b8" }}>No Events Found</div>
          <div style={{ fontSize: "13px", marginTop: "4px" }}>
            {selectedCamera || selectedType || lockedFilter || startTime || endTime
              ? "Try adjusting your filter criteria."
              : "Events triggered by your cameras will appear here automatically."}
          </div>
        </div>
      )}

      {/* Event Cards Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "16px",
        }}
      >
        {events.map((evt) => (
          <EventCard
            key={evt.id}
            event={evt}
            cameraName={cameraMap.get(evt.camera_serial)}
            isRead={readEventIds.has(evt.id)}
            onSelect={(e) => onEventRead && onEventRead(e.id)}
            onLockToggle={handleLockToggle}
          />
        ))}
      </div>

      {/* Load More Button */}
      {events.length < total && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: "12px" }}>
          <button
            onClick={handleLoadMore}
            disabled={loading}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: "6px",
              padding: "10px 24px",
              fontSize: "14px",
              fontWeight: 600,
              cursor: loading ? "wait" : "pointer",
              boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
            }}
          >
            {loading ? "Loading More..." : `Load More (${total - events.length} remaining)`}
          </button>
        </div>
      )}
    </div>
  );
};

