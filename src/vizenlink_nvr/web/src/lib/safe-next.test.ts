import { describe, it, expect } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it("accepts valid application paths and deep links", () => {
    expect(safeNext("/")).toBe("/");
    expect(safeNext("/playback?camera=X&t=T")).toBe("/playback?camera=X&t=T");
    expect(safeNext("/cameras")).toBe("/cameras");
    expect(safeNext("/dashboard")).toBe("/dashboard");
    expect(safeNext("/events?unread=true")).toBe("/events?unread=true");
  });

  it("rejects empty, undefined, and non-string values", () => {
    expect(safeNext("")).toBeNull();
    expect(safeNext(undefined)).toBeNull();
    expect(safeNext(null)).toBeNull();
  });

  it("rejects protocol-relative and scheme-relative URLs", () => {
    expect(safeNext("//evil.example")).toBeNull();
    expect(safeNext("//evil.example/path")).toBeNull();
  });

  it("rejects absolute URLs with scheme", () => {
    expect(safeNext("https://evil.example")).toBeNull();
    expect(safeNext("http://evil.example")).toBeNull();
    expect(safeNext("javascript:alert(1)")).toBeNull();
  });

  it("rejects paths containing backslashes", () => {
    expect(safeNext("/\\evil")).toBeNull();
    expect(safeNext("/foo\\bar")).toBeNull();
    expect(safeNext("\\evil")).toBeNull();
  });

  it("rejects paths to /login, /setup, and /api", () => {
    expect(safeNext("/login")).toBeNull();
    expect(safeNext("/login?x=1")).toBeNull();
    expect(safeNext("/login/subpath")).toBeNull();
    expect(safeNext("/setup")).toBeNull();
    expect(safeNext("/setup?step=1")).toBeNull();
    expect(safeNext("/setup/welcome")).toBeNull();
    expect(safeNext("/api")).toBeNull();
    expect(safeNext("/api/v1/auth/status")).toBeNull();
    expect(safeNext("/api/v1/cameras")).toBeNull();
  });
});
