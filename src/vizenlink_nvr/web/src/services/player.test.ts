import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { TilePlayer, type PlayerState } from "./player";

// Mock RTCPeerConnection
class MockRTCPeerConnection {
  static instances: MockRTCPeerConnection[] = [];
  config: RTCConfiguration | undefined;
  connectionState: RTCPeerConnectionState = "new";
  ontrack: ((event: any) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  closeCalled = false;
  transceivers: any[] = [];

  constructor(config?: RTCConfiguration) {
    this.config = config;
    MockRTCPeerConnection.instances.push(this);
  }

  addTransceiver(trackOrKind: any, init?: any) {
    this.transceivers.push({ trackOrKind, init });
    return {};
  }

  async createOffer() {
    return { type: "offer" as const, sdp: "v=0\r\no=mock 0 0 IN IP4 127.0.0.1\r\ns=Mock\r\n" };
  }

  async setLocalDescription(_desc: any) {}

  async setRemoteDescription(_desc: any) {}

  close() {
    this.closeCalled = true;
  }
}

describe("TilePlayer", () => {
  let originalRTCPeerConnection: any;

  beforeEach(() => {
    vi.useFakeTimers();
    MockRTCPeerConnection.instances = [];
    originalRTCPeerConnection = globalThis.RTCPeerConnection;
    globalThis.RTCPeerConnection = MockRTCPeerConnection as any;
    globalThis.RTCSessionDescription = class {
      type: string;
      sdp: string;
      constructor(init: any) {
        this.type = init?.type;
        this.sdp = init?.sdp || "";
      }
    } as any;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    globalThis.RTCPeerConnection = originalRTCPeerConnection;
  });

  it("constructs RTCPeerConnection with empty iceServers and posts to returned token path without altering case", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any, init?: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        return new Response(
          JSON.stringify({
            token: "tok_ABC123",
            expires_in: 900,
            stream: "sub",
            path: "cam/CAM_FrontDoor/sub",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (urlStr.includes("/whep")) {
        expect(urlStr).toBe("/cam/CAM_FrontDoor/sub/whep?token=tok_ABC123");
        expect(init?.method).toBe("POST");
        expect(init?.headers?.["Content-Type"]).toBe("application/sdp");
        return new Response("v=0\r\ns=Answer\r\n", {
          status: 201,
          headers: {
            "Content-Type": "application/sdp",
            Location: "/cam/CAM_FrontDoor/sub/whep/session_456",
          },
        });
      }
      return new Response(null, { status: 404 });
    });

    const states: PlayerState[] = [];
    const player = new TilePlayer({
      serial: "CAM_FrontDoor",
      stream: "sub",
      onStateChange: (s) => states.push(s),
    });

    const video = document.createElement("video");
    await player.attach(video);

    expect(MockRTCPeerConnection.instances).toHaveLength(1);
    const pc = MockRTCPeerConnection.instances[0];
    expect(pc.config?.iceServers).toEqual([]);

    player.cleanup();
  });

  it("does not construct RTCPeerConnection if cleaned up while token fetch is pending", async () => {
    let resolveTokenFetch: any;
    vi.spyOn(globalThis, "fetch").mockImplementation((url: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        return new Promise((resolve) => {
          resolveTokenFetch = () =>
            resolve(
              new Response(
                JSON.stringify({
                  token: "tok_delayed",
                  expires_in: 900,
                  stream: "sub",
                  path: "cam/CAM1/sub",
                }),
                { status: 200 }
              )
            );
        });
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const player = new TilePlayer({
      serial: "CAM1",
      stream: "sub",
    });

    const video = document.createElement("video");
    const attachPromise = player.attach(video);

    // Unmount/cleanup immediately before token fetch resolves
    player.cleanup();

    // Now resolve the fetch
    resolveTokenFetch();
    await attachPromise;

    expect(MockRTCPeerConnection.instances).toHaveLength(0);
  });

  it("closes RTCPeerConnection and DELETEs WHEP location on cleanup without firing timers", async () => {
    let deleteCalled = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any, init?: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        return new Response(
          JSON.stringify({ token: "tok_1", path: "cam/CAM1/sub" }),
          { status: 200 }
        );
      }
      if (urlStr.includes("/whep/session_123")) {
        if (init?.method === "DELETE") {
          deleteCalled = true;
          return new Response(null, { status: 200 });
        }
      }
      if (urlStr.includes("/whep")) {
        return new Response("v=0\r\ns=Answer\r\n", {
          status: 201,
          headers: { Location: "/cam/CAM1/sub/whep/session_123" },
        });
      }
      return new Response(null, { status: 404 });
    });

    const player = new TilePlayer({
      serial: "CAM1",
      stream: "sub",
    });

    const video = document.createElement("video");
    await player.attach(video);

    const pc = MockRTCPeerConnection.instances[0];
    expect(pc.closeCalled).toBe(false);

    player.cleanup();

    expect(pc.closeCalled).toBe(true);
    expect(deleteCalled).toBe(true);

    // Advancing timers should not fire anything
    vi.advanceTimersByTime(60000);
  });

  it("reconnects with exponential backoff on failure and transitions to offline after 3 attempts", async () => {
    let tokenFetchCount = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        tokenFetchCount++;
        // Fail every request
        return new Response(null, { status: 503 });
      }
      return new Response(null, { status: 404 });
    });

    const states: PlayerState[] = [];
    const player = new TilePlayer({
      serial: "CAM1",
      stream: "sub",
      onStateChange: (s) => states.push(s),
    });

    const video = document.createElement("video");
    await player.attach(video);

    // Initial attempt failed: 1 failure
    expect(tokenFetchCount).toBe(1);
    expect(player.getState()).toBe("reconnecting");

    // Attempt 1: backoff is 1s
    await vi.advanceTimersByTimeAsync(1000);
    expect(tokenFetchCount).toBe(2);
    expect(player.getState()).toBe("reconnecting");

    // Attempt 2: backoff is 2s
    await vi.advanceTimersByTimeAsync(2000);
    expect(tokenFetchCount).toBe(3);
    // After 3 consecutive failures: state is offline while retries continue
    expect(player.getState()).toBe("offline");

    // Attempt 3: backoff is 4s
    await vi.advanceTimersByTimeAsync(4000);
    expect(tokenFetchCount).toBe(4);
    expect(player.getState()).toBe("offline");

    player.cleanup();
  });

  it("retryNow() cancels pending backoff and restarts immediately", async () => {
    let tokenFetchCount = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        tokenFetchCount++;
        return new Response(null, { status: 500 });
      }
      return new Response(null, { status: 404 });
    });

    const player = new TilePlayer({
      serial: "CAM1",
      stream: "sub",
    });

    const video = document.createElement("video");
    await player.attach(video);
    expect(tokenFetchCount).toBe(1);

    // Still during backoff before timer fires
    player.retryNow();
    expect(tokenFetchCount).toBe(2);

    player.cleanup();
  });

  it("switchStream('main') restarts with new stream configuration", async () => {
    const requestedStreams: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any) => {
      const urlStr = url.toString();
      if (urlStr.includes("/media-token")) {
        const stream = new URL(urlStr, "http://localhost").searchParams.get("stream") || "";
        requestedStreams.push(stream);
        return new Response(
          JSON.stringify({ token: "tok_x", path: `cam/CAM1/${stream}` }),
          { status: 200 }
        );
      }
      if (urlStr.includes("/whep")) {
        return new Response("v=0\r\ns=Answer\r\n", { status: 201 });
      }
      return new Response(null, { status: 404 });
    });

    const player = new TilePlayer({
      serial: "CAM1",
      stream: "sub",
    });

    const video = document.createElement("video");
    await player.attach(video);
    expect(requestedStreams).toEqual(["sub"]);

    await player.switchStream("main");
    expect(requestedStreams).toEqual(["sub", "main"]);

    player.cleanup();
  });
});