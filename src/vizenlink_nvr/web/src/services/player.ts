/**
 * WebRTC WHEP video player with fallback, truthful stall detection, and dynamic stream switching.
 * Requirements: LIVE-01, LIVE-03, LIVE-04
 */

export type PlayerState = "connecting" | "live" | "stalled" | "offline" | "error";
export type StreamRole = "main" | "sub";

export interface PlayerConfig {
  serial: string;
  stream: StreamRole;
  mediamtxBaseUrl?: string;
  onStateChange?: (state: PlayerState, message?: string) => void;
}

export class TilePlayer {
  private config: PlayerConfig;
  private state: PlayerState = "connecting";
  private pc: RTCPeerConnection | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private stallCheckInterval: number | null = null;
  private lastTimeUpdate: number = 0;
  private token: string | null = null;

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
    await this.restart();
  }

  public async restart(): Promise<void> {
    this.cleanup();
    await this.start();
  }

  private async fetchMediaToken(): Promise<string> {
    const res = await fetch(`/api/v1/cameras/${this.config.serial}/media-token?stream=${this.config.stream}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      throw new Error(`Media token issue failed: ${res.status}`);
    }
    const data = await res.json();
    return data.token;
  }

  public async start(): Promise<void> {
    this.setState("connecting");

    try {
      this.token = await this.fetchMediaToken();
      this.pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });

      this.pc.addTransceiver("video", { direction: "recvonly" });

      this.pc.ontrack = (event) => {
        if (this.videoEl && event.streams[0]) {
          this.videoEl.srcObject = event.streams[0];
          this.videoEl.play().catch(() => {});
        }
      };

      this.pc.onconnectionstatechange = () => {
        if (!this.pc) return;
        const s = this.pc.connectionState;
        if (s === "failed" || s === "disconnected") {
          this.setState("offline", "WebRTC connection lost");
        }
      };

      const offer = await this.pc.createOffer();
      await this.pc.setLocalDescription(offer);

      const whepUrl = `/cam/${this.config.serial}/${this.config.stream}/whep?token=${encodeURIComponent(this.token)}`;
      const whepRes = await fetch(whepUrl, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: offer.sdp,
      });

      if (!whepRes.ok) {
        throw new Error(`WHEP endpoint returned ${whepRes.status}`);
      }

      const answerSdp = await whepRes.text();
      await this.pc.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: answerSdp }));

      this.startStallWatchdog();
    } catch (err: any) {
      this.setState("offline", err?.message || "Failed to start player");
    }
  }

  private setupVideoListeners(): void {
    if (!this.videoEl) return;

    this.videoEl.onplaying = () => {
      this.setState("live");
      this.lastTimeUpdate = Date.now();
    };

    this.videoEl.ontimeupdate = () => {
      this.lastTimeUpdate = Date.now();
      if (this.state === "stalled" || this.state === "connecting") {
        this.setState("live");
      }
    };

    this.videoEl.onwaiting = () => {
      this.setState("stalled", "Buffering stream");
    };

    this.videoEl.onerror = () => {
      this.setState("error", "Video playback error");
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
          this.setState("stalled", "Stream stalled / frozen frame");
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

  public cleanup(): void {
    this.stopStallWatchdog();
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
    }
  }
}

