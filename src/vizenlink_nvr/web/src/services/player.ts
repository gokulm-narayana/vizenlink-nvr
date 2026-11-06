/**
 * WebRTC WHEP video player with fallback, truthful stall detection, and dynamic stream switching.
 * Requirements: LIVE-01, LIVE-03, LIVE-04, D-17
 */

export type PlayerState = "connecting" | "live" | "stalled" | "reconnecting" | "offline" | "error";
export type StreamRole = "main" | "sub";

export interface PlayerConfig {
  serial: string;
  stream: StreamRole;
  mediamtxBaseUrl?: string;
  onStateChange?: (state: PlayerState, message?: string) => void;
}

const BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];

function getBackoffDelay(failureCount: number): number {
  const index = Math.min(Math.max(0, failureCount - 1), BACKOFF_DELAYS.length - 1);
  return BACKOFF_DELAYS[index];
}

export class TilePlayer {
  private config: PlayerConfig;
  private state: PlayerState = "connecting";
  private pc: RTCPeerConnection | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private stallCheckInterval: number | null = null;
  private reconnectTimer: number | null = null;
  private lastTimeUpdate: number = 0;
  private token: string | null = null;
  private whepLocation: string | null = null;
  private attemptId: number = 0;
  private consecutiveFailures: number = 0;
  private disposed: boolean = false;

  constructor(config: PlayerConfig) {
    this.config = config;
  }

  public getState(): PlayerState {
    return this.state;
  }

  private setState(newState: PlayerState, message?: string): void {
    if (this.state === newState) return;
    this.state = newState;
    if (this.config.onStateChange) {
      this.config.onStateChange(newState, message);
    }
  }

  public async attach(videoEl: HTMLVideoElement): Promise<void> {
    this.videoEl = videoEl;
    this.setupVideoListeners();
    await this.start();
  }

  public async switchStream(newStream: StreamRole): Promise<void> {
    if (this.config.stream === newStream) return;
    this.config.stream = newStream;
    this.consecutiveFailures = 0;
    await this.restart();
  }

  public async restart(): Promise<void> {
    this.cleanupPeer();
    this.disposed = false;
    await this.start();
  }

  public retryNow(): void {
    this.clearReconnectTimer();
    this.cleanupPeer();
    this.disposed = false;
    void this.start();
  }

  private async fetchMediaToken(): Promise<{ token: string; path: string }> {
    const res = await fetch(`/api/v1/cameras/${this.config.serial}/media-token?stream=${this.config.stream}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      throw new Error(`Media token issue failed: ${res.status}`);
    }
    const data = await res.json();
    return { token: data.token, path: data.path };
  }

  public async start(): Promise<void> {
    const currentAttempt = ++this.attemptId;
    this.clearReconnectTimer();
    this.stopStallWatchdog();
    this.cleanupPeer();

    const initialState: PlayerState =
      this.consecutiveFailures >= 3
        ? "offline"
        : this.consecutiveFailures > 0
          ? "reconnecting"
          : "connecting";
    this.setState(initialState);

    try {
      const { token, path } = await this.fetchMediaToken();
      if (this.disposed || currentAttempt !== this.attemptId) {
        return;
      }

      this.token = token;

      // Construct peer connection with empty iceServers (LAN-only, D-17)
      const pc = new RTCPeerConnection({
        iceServers: [],
      });
      this.pc = pc;

      pc.addTransceiver("video", { direction: "recvonly" });

      pc.ontrack = (event) => {
        if (this.disposed || currentAttempt !== this.attemptId) return;
        if (this.videoEl && event.streams[0]) {
          this.videoEl.srcObject = event.streams[0];
          this.videoEl.play().catch(() => {});
        }
      };

      pc.onconnectionstatechange = () => {
        if (this.disposed || currentAttempt !== this.attemptId) return;
        const s = pc.connectionState;
        if (s === "failed" || s === "disconnected") {
          this.handleFailure("WebRTC connection lost");
        }
      };

      const offer = await pc.createOffer();
      if (this.disposed || currentAttempt !== this.attemptId) {
        pc.close();
        return;
      }

      await pc.setLocalDescription(offer);
      if (this.disposed || currentAttempt !== this.attemptId) {
        pc.close();
        return;
      }

      const whepUrl = `/${path}/whep?token=${encodeURIComponent(token)}`;
      const whepRes = await fetch(whepUrl, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: offer.sdp,
      });

      if (this.disposed || currentAttempt !== this.attemptId) {
        pc.close();
        const loc = whepRes.headers.get("Location");
        if (loc) {
          void fetch(loc, { method: "DELETE" }).catch(() => {});
        }
        return;
      }

      if (!whepRes.ok) {
        throw new Error(`WHEP endpoint returned ${whepRes.status}`);
      }

      const loc = whepRes.headers.get("Location");
      if (loc) {
        this.whepLocation = loc;
      }

      const answerSdp = await whepRes.text();
      if (this.disposed || currentAttempt !== this.attemptId) {
        pc.close();
        if (this.whepLocation) {
          void fetch(this.whepLocation, { method: "DELETE" }).catch(() => {});
          this.whepLocation = null;
        }
        return;
      }

      await pc.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: answerSdp }));
      if (this.disposed || currentAttempt !== this.attemptId) {
        pc.close();
        if (this.whepLocation) {
          void fetch(this.whepLocation, { method: "DELETE" }).catch(() => {});
          this.whepLocation = null;
        }
        return;
      }

      this.startStallWatchdog();
    } catch (err: any) {
      if (this.disposed || currentAttempt !== this.attemptId) return;
      this.handleFailure(err?.message || "Failed to start player");
    }
  }

  private handleFailure(message?: string): void {
    this.stopStallWatchdog();
    this.cleanupPeer();

    this.consecutiveFailures++;
    const isOffline = this.consecutiveFailures >= 3;
    this.setState(isOffline ? "offline" : "reconnecting", message);

    const delay = getBackoffDelay(this.consecutiveFailures);
    this.clearReconnectTimer();
    this.reconnectTimer = window.setTimeout(() => {
      if (!this.disposed) {
        void this.start();
      }
    }, delay);
  }

  private setupVideoListeners(): void {
    if (!this.videoEl) return;

    this.videoEl.onplaying = () => {
      this.consecutiveFailures = 0;
      this.setState("live");
      this.lastTimeUpdate = Date.now();
    };

    this.videoEl.ontimeupdate = () => {
      this.lastTimeUpdate = Date.now();
      if (this.state === "stalled" || this.state === "connecting" || this.state === "reconnecting") {
        this.consecutiveFailures = 0;
        this.setState("live");
      }
    };

    this.videoEl.onwaiting = () => {
      this.setState("stalled", "Buffering stream");
    };

    this.videoEl.onerror = () => {
      this.handleFailure("Video playback error");
    };
  }

  private startStallWatchdog(): void {
    this.stopStallWatchdog();
    this.lastTimeUpdate = Date.now();

    this.stallCheckInterval = window.setInterval(() => {
      if (this.state === "live") {
        const elapsed = Date.now() - this.lastTimeUpdate;
        // Never present a frozen frame as live if stalled > 5s (LIVE-04)
        if (elapsed > 5000) {
          this.handleFailure("Stream stalled / frozen frame");
        }
      }
    }, 1000);
  }

  private stopStallWatchdog(): void {
    if (this.stallCheckInterval !== null) {
      clearInterval(this.stallCheckInterval);
      this.stallCheckInterval = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private cleanupPeer(): void {
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
    if (this.whepLocation) {
      const loc = this.whepLocation;
      this.whepLocation = null;
      void fetch(loc, { method: "DELETE" }).catch(() => {});
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
    }
  }

  public cleanup(): void {
    this.disposed = true;
    this.attemptId++;
    this.stopStallWatchdog();
    this.clearReconnectTimer();
    this.cleanupPeer();
  }
}
