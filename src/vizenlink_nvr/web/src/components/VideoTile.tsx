import React, { useEffect, useRef, useState } from "react";
import { PlayerState, StreamRole, TilePlayer } from "../services/player";
import { TileControls } from "./TileControls";

interface VideoTileProps {
  serial: string;
  name: string;
  isRecording?: boolean;
  isMaximized?: boolean;
  onToggleMaximize?: () => void;
}

export const VideoTile: React.FC<VideoTileProps> = ({
  serial,
  name,
  isRecording = false,
  isMaximized = false,
  onToggleMaximize,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playerRef = useRef<TilePlayer | null>(null);

  const [playerState, setPlayerState] = useState<PlayerState>("connecting");
  const [streamRole, setStreamRole] = useState<StreamRole>("sub");
  const [isMuted, setIsMuted] = useState(true);

  // Initialize or re-init player when serial changes
  useEffect(() => {
    const role: StreamRole = isMaximized ? "main" : "sub";
    setStreamRole(role);

    const player = new TilePlayer({
      serial,
      stream: role,
      onStateChange: (state) => setPlayerState(state),
    });
    playerRef.current = player;

    if (videoRef.current) {
      player.attach(videoRef.current);
    }

    return () => {
      player.cleanup();
    };
  }, [serial]);

  // Handle maximize stream auto-switch (LIVE-03: sub in grid, main when maximized)
  useEffect(() => {
    const targetRole: StreamRole = isMaximized ? "main" : "sub";
    if (targetRole !== streamRole && playerRef.current) {
      setStreamRole(targetRole);
      playerRef.current.switchStream(targetRole);
    }
  }, [isMaximized]);

  const handleToggleMute = () => {
    if (videoRef.current) {
      const nextMuted = !isMuted;
      videoRef.current.muted = nextMuted;
      setIsMuted(nextMuted);
    }
  };

  const handleSnapshot = () => {
    if (!videoRef.current) return;
    const v = videoRef.current;
    if (v.videoWidth === 0 || v.videoHeight === 0) return;

    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.95);

    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `snapshot_${serial}_${Date.now()}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        backgroundColor: "#000",
        borderRadius: "4px",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={isMuted}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          backgroundColor: "#000",
        }}
      />

      <TileControls
        serial={serial}
        name={name}
        state={playerState}
        stream={streamRole}
        isRecording={isRecording}
        isMuted={isMuted}
        isMaximized={isMaximized}
        onToggleMute={handleToggleMute}
        onToggleMaximize={onToggleMaximize || (() => {})}
        onSnapshot={handleSnapshot}
      />
    </div>
  );
};
