export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  unauthorizedHandler = fn;
}

export type ApiFetchInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | unknown;
};

export async function apiFetch<T>(path: string, init?: ApiFetchInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const rawBody = init?.body;
  let requestBody: BodyInit | null | undefined;

  if (
    rawBody !== undefined &&
    rawBody !== null &&
    typeof rawBody === "object" &&
    !(rawBody instanceof Blob) &&
    !(rawBody instanceof FormData) &&
    !(rawBody instanceof URLSearchParams) &&
    !(rawBody instanceof ArrayBuffer)
  ) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    requestBody = JSON.stringify(rawBody);
  } else {
    requestBody = rawBody as BodyInit | null | undefined;
  }

  const res = await fetch(path, {
    ...init,
    headers,
    body: requestBody,
    credentials: init?.credentials ?? "same-origin",
  });

  if (!res.ok) {
    let detail = res.statusText || `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data && typeof data === "object") {
        if (typeof data.detail === "string") {
          detail = data.detail;
        } else if (Array.isArray(data.detail) && data.detail.length > 0) {
          const first = data.detail[0];
          detail = typeof first === "string" ? first : (first?.msg || JSON.stringify(first));
        } else if (typeof data.message === "string") {
          detail = data.message;
        }
      }
    } catch {
      // not JSON or body already drained
    }

    const isAuthEndpoint = /\/auth\/(status|login|setup|logout)($|\?)/.test(path);
    if (res.status === 401 && !isAuthEndpoint && unauthorizedHandler) {
      unauthorizedHandler();
    }

    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}