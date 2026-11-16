import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

interface ProviderSummary {
  id: "openai" | "gemini" | "claude" | "ollama";
  name: string;
  models: string[];
  selected_model: string | null;
  auto_model?: boolean;
  has_api_key: boolean;
  api_key_masked: string | null;
  requires_key: boolean;
  active: boolean;
}

interface DetectModelsResponse {
  provider: string;
  recommended_model: string;
  models: string[];
  verified: boolean;
}

interface ModelStatus {
  model_configured: boolean;
  model: string | null;
  managed_by_environment?: boolean;
  active_provider?: string;
  providers?: ProviderSummary[];
}

const DEFAULT_PROVIDERS: ProviderSummary[] = [
  {
    id: "openai",
    name: "OpenAI (ChatGPT)",
    models: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"],
    selected_model: "gpt-4o-mini",
    has_api_key: false,
    api_key_masked: null,
    requires_key: true,
    active: false,
  },
  {
    id: "gemini",
    name: "Google Gemini",
    models: [
      "gemini-3.5-flash-lite",
      "gemini-3.1-flash-lite",
      "gemini-3-flash-preview",
      "gemini-3.6-flash",
      "gemini-3.8-flash",
      "gemini-3.1-pro-preview",
    ],
    selected_model: "gemini-3.5-flash-lite",
    has_api_key: false,
    api_key_masked: null,
    requires_key: true,
    active: false,
  },
  {
    id: "claude",
    name: "Anthropic Claude",
    models: [
      "claude-sonnet-4-20250514",
      "claude-3-5-haiku-20241022",
      "claude-3-7-sonnet-20250219",
    ],
    selected_model: "claude-sonnet-4-20250514",
    has_api_key: false,
    api_key_masked: null,
    requires_key: true,
    active: false,
  },
  {
    id: "ollama",
    name: "Local AI (Ollama)",
    models: [],
    selected_model: null,
    has_api_key: false,
    api_key_masked: null,
    requires_key: false,
    active: false,
  },
];

const PROVIDER_SHORT_LABEL: Record<string, string> = {
  openai: "ChatGPT",
  gemini: "Gemini",
  claude: "Claude",
  ollama: "Local AI",
};

export function AiProvidersSettings() {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const [providerTab, setProviderTab] = useState<"openai" | "gemini" | "claude" | "ollama">(
    "openai",
  );
  const [cloudModel, setCloudModel] = useState("auto");
  const [selectedModel, setSelectedModel] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [detectedForTab, setDetectedForTab] = useState<{
    provider: string;
    recommended: string;
    models: string[];
    verified: boolean;
  } | null>(null);
  const [detectError, setDetectError] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const detectAbortRef = useRef<AbortController | null>(null);
  const lastProbedRef = useRef<string>("");

  const status = useQuery({
    queryKey: ["assistant", "status"],
    queryFn: () => apiFetch<ModelStatus>("/api/v1/assistant/status"),
    staleTime: 30000,
  });

  const models = useQuery({
    queryKey: ["assistant", "models"],
    queryFn: () => apiFetch<{ models: string[] }>("/api/v1/assistant/models"),
    enabled: user?.role === "owner",
    retry: false,
    staleTime: 30000,
  });

  const providers = useMemo(
    () => (status.data?.providers?.length ? status.data.providers : DEFAULT_PROVIDERS),
    [status.data?.providers],
  );

  const activeProviderSummary = useMemo(
    () => providers.find((p) => p.active || p.id === status.data?.active_provider),
    [providers, status.data?.active_provider],
  );

  const selectedTabSummary = useMemo(
    () => providers.find((p) => p.id === providerTab) ?? providers[0],
    [providers, providerTab],
  );

  const detectModels = useCallback(
    async (provider: "openai" | "gemini" | "claude", apiKey?: string) => {
      detectAbortRef.current?.abort();
      const controller = new AbortController();
      detectAbortRef.current = controller;
      setIsDetecting(true);
      setDetectError(null);
      try {
        const result = await apiFetch<DetectModelsResponse>("/api/v1/assistant/provider/detect", {
          method: "POST",
          body: { provider, api_key: apiKey || undefined },
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setDetectedForTab({
          provider,
          recommended: result.recommended_model,
          models: result.models,
          verified: result.verified,
        });
        setCloudModel("auto");
      } catch (err) {
        if (controller.signal.aborted || (err instanceof Error && err.name === "AbortError")) {
          return;
        }
        setDetectedForTab(null);
        setDetectError(err instanceof Error ? err.message : "Couldn't detect available models.");
      } finally {
        if (!controller.signal.aborted) {
          setIsDetecting(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const active = status.data?.active_provider;
    if (
      active === "openai" ||
      active === "gemini" ||
      active === "claude" ||
      active === "ollama"
    ) {
      setProviderTab(active);
    }
  }, [status.data?.active_provider]);

  useEffect(() => {
    detectAbortRef.current?.abort();
    lastProbedRef.current = "";
    setDetectedForTab(null);
    setDetectError(null);
    setIsDetecting(false);
    if (selectedTabSummary.id !== "ollama") {
      setCloudModel(
        selectedTabSummary.auto_model !== false || !selectedTabSummary.selected_model
          ? "auto"
          : selectedTabSummary.selected_model,
      );
    } else if (selectedTabSummary.selected_model) {
      setSelectedModel(selectedTabSummary.selected_model);
    }
    setApiKeyInput("");
    setShowApiKey(false);
  }, [
    selectedTabSummary.id,
    selectedTabSummary.selected_model,
    selectedTabSummary.auto_model,
    selectedTabSummary.models,
  ]);

  useEffect(() => {
    if (providerTab === "ollama") return;
    const trimmed = apiKeyInput.trim();
    if (!trimmed) {
      detectAbortRef.current?.abort();
      lastProbedRef.current = "";
      setDetectedForTab(null);
      setDetectError(null);
      setIsDetecting(false);
      return;
    }
    if (trimmed.length < 20) return;
    const cacheKey = `${providerTab}:${trimmed}`;
    if (lastProbedRef.current === cacheKey) return;
    const timer = window.setTimeout(() => {
      lastProbedRef.current = cacheKey;
      void detectModels(providerTab, trimmed);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [providerTab, apiKeyInput, detectModels]);

  const availableCloudModels = useMemo(() => {
    if (detectedForTab?.provider === selectedTabSummary.id && detectedForTab.models.length > 0) {
      return detectedForTab.models;
    }
    return selectedTabSummary.models;
  }, [detectedForTab, selectedTabSummary.id, selectedTabSummary.models]);

  const autoModelName = useMemo(() => {
    if (detectedForTab?.provider === selectedTabSummary.id) {
      return detectedForTab.recommended;
    }
    return selectedTabSummary.selected_model || selectedTabSummary.models[0] || "";
  }, [
    detectedForTab,
    selectedTabSummary.id,
    selectedTabSummary.selected_model,
    selectedTabSummary.models,
  ]);

  const connection = useMutation({
    mutationFn: (model: string | null) =>
      apiFetch<ModelStatus>("/api/v1/assistant/model", { method: "PUT", body: { model } }),
    onSuccess: (next) => {
      queryClient.setQueryData(["assistant", "status"], next);
    },
  });

  const providerConfig = useMutation({
    mutationFn: (payload: {
      provider: string;
      model?: string | null;
      api_key?: string | null;
      clear_key?: boolean;
    }) => apiFetch<ModelStatus>("/api/v1/assistant/provider", { method: "PUT", body: payload }),
    onSuccess: (next) => {
      queryClient.setQueryData(["assistant", "status"], next);
      setApiKeyInput("");
      setDetectError(null);
    },
  });

  const canManageProviders = user?.role === "owner" && !status.data?.managed_by_environment;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">AI Providers & API Keys</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Connect your own ChatGPT, Google Gemini, or Anthropic Claude key, or link a local Ollama model for the AI Assistant.
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/assistant">
            <Sparkles className="size-4" />
            Open AI Assistant
            <ArrowUpRight className="size-4" />
          </Link>
        </Button>
      </div>

      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <KeyRound className="size-5 text-primary" />
            <h3 className="text-sm font-semibold">Active AI Provider</h3>
          </div>
          {status.data?.model_configured ? (
            <Badge variant="outline" className="text-xs font-normal text-success">
              Connected · {activeProviderSummary?.name ?? status.data.active_provider} ({status.data.model})
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs font-normal text-muted-foreground">
              Built-in Recorder & Camera Tools only
            </Badge>
          )}
        </div>

        {status.error && (
          <p role="alert" className="mt-4 text-xs text-critical">
            Couldn't check model configuration.
          </p>
        )}

        <div
          className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"
          role="tablist"
          aria-label="AI provider selection"
        >
          {providers.map((provider) => {
            const isSelected = provider.id === providerTab;
            const isReady = provider.active || provider.has_api_key;
            return (
              <button
                key={provider.id}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => setProviderTab(provider.id)}
                className={`flex items-center justify-between rounded-lg border px-4 py-2 text-left text-sm transition-colors ${
                  isSelected
                    ? "border-primary bg-selected text-selected-foreground font-semibold"
                    : "border-border bg-background/40 text-foreground hover:border-primary/60"
                }`}
              >
                <span>{PROVIDER_SHORT_LABEL[provider.id] || provider.name}</span>
                {isReady && (
                  <span className="size-2 rounded-full bg-success" aria-label="Configured" />
                )}
              </button>
            );
          })}
        </div>

        {canManageProviders ? (
          selectedTabSummary.id === "ollama" ? (
            <div className="mt-6 flex flex-col gap-4 max-w-xl">
              <label className="vms-field">
                Installed Ollama model
                <NativeSelect
                  aria-label="Local AI model"
                  className="w-full"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  <option value="">Choose a model…</option>
                  {models.data?.models?.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </NativeSelect>
              </label>

              {models.isPending && (
                <p className="text-xs text-muted-foreground">Checking installed models…</p>
              )}
              {models.error && (
                <p className="text-xs text-muted-foreground">{models.error.message}</p>
              )}
              {!models.isPending && !models.error && !models.data?.models?.length && (
                <p className="text-xs text-muted-foreground">
                  No models are installed in Ollama yet.
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={!selectedModel || connection.isPending}
                  onClick={() => connection.mutate(selectedModel)}
                >
                  Connect selected model
                </Button>
                {status.data?.model_configured && status.data?.active_provider === "ollama" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={connection.isPending}
                    onClick={() => connection.mutate(null)}
                  >
                    Disconnect model
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={models.isFetching}
                  onClick={() => void models.refetch()}
                >
                  Refresh model list
                </Button>
              </div>

              {connection.error && (
                <p role="alert" className="text-xs text-critical">
                  {connection.error.message}
                </p>
              )}
              {connection.isSuccess && (
                <p role="status" className="text-xs text-success">
                  {status.data?.model_configured
                    ? "Model connected on this NVR."
                    : "Model disconnected. Recorder commands still work."}
                </p>
              )}
            </div>
          ) : (
            <form
              className="mt-6 flex flex-col gap-4 max-w-xl"
              onSubmit={(e) => {
                e.preventDefault();
                if (!apiKeyInput.trim() && !selectedTabSummary.has_api_key) return;
                detectAbortRef.current?.abort();
                setIsDetecting(false);
                providerConfig.mutate({
                  provider: selectedTabSummary.id,
                  model: cloudModel || "auto",
                  api_key: apiKeyInput.trim() || undefined,
                });
              }}
            >
              <div className="flex flex-col gap-1">
                <label
                  className="text-xs font-semibold text-muted-foreground"
                  htmlFor="byok-api-key"
                >
                  {selectedTabSummary.name} API key
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    id="byok-api-key"
                    type={showApiKey ? "text" : "password"}
                    aria-label="Provider API key"
                    placeholder={
                      selectedTabSummary.has_api_key
                        ? `Saved: ${selectedTabSummary.api_key_masked}`
                        : `Paste ${PROVIDER_SHORT_LABEL[selectedTabSummary.id] ?? ""} API key — models detect automatically…`
                    }
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                  />
                  <Button
                    type="button"
                    size="icon"
                    variant="outline"
                    aria-label={showApiKey ? "Hide API key" : "Show API key"}
                    onClick={() => setShowApiKey((v) => !v)}
                  >
                    {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Paste your key — compatible models are detected automatically without manual model setup.
                </p>
              </div>

              {isDetecting && (
                <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Detecting available {PROVIDER_SHORT_LABEL[selectedTabSummary.id] ?? ""} models for this key…
                </p>
              )}
              {detectError && (
                <p role="alert" className="text-xs text-critical">
                  {detectError}
                </p>
              )}
              {detectedForTab?.provider === selectedTabSummary.id && !isDetecting && !detectError && (
                <p role="status" className="text-xs text-success">
                  Detected {detectedForTab.models.length} compatible{" "}
                  {detectedForTab.models.length === 1 ? "model" : "models"} · Auto-selected{" "}
                  <span className="font-semibold">{detectedForTab.recommended}</span>
                </p>
              )}

              <label className="vms-field">
                Model (optional — auto-detected by default)
                <NativeSelect
                  aria-label="Provider model"
                  className="w-full"
                  value={cloudModel}
                  onChange={(e) => setCloudModel(e.target.value)}
                >
                  <option value="auto">
                    {autoModelName
                      ? `Auto-detect best model (${autoModelName})`
                      : "Auto-detect best model (recommended)"}
                  </option>
                  {availableCloudModels.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </NativeSelect>
              </label>

              {selectedTabSummary.has_api_key && !detectedForTab && (
                <p className="text-xs text-success">
                  Saved key: {selectedTabSummary.api_key_masked} · Active model:{" "}
                  <span className="font-semibold">
                    {selectedTabSummary.selected_model || autoModelName}
                  </span>
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  size="sm"
                  disabled={
                    providerConfig.isPending ||
                    (!apiKeyInput.trim() && !selectedTabSummary.has_api_key)
                  }
                >
                  {providerConfig.isPending
                    ? "Connecting…"
                    : selectedTabSummary.has_api_key && !apiKeyInput.trim()
                      ? `Use ${PROVIDER_SHORT_LABEL[selectedTabSummary.id]}`
                      : "Save & connect"}
                </Button>

                {(apiKeyInput.trim().length > 0 || selectedTabSummary.has_api_key) && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isDetecting || providerConfig.isPending}
                      onClick={() => {
                        if (selectedTabSummary.id === "ollama") return;
                        const trimmed = apiKeyInput.trim();
                        if (trimmed) {
                          lastProbedRef.current = `${selectedTabSummary.id}:${trimmed}`;
                        }
                        void detectModels(selectedTabSummary.id, trimmed || undefined);
                      }}
                    >
                      <RefreshCw className={`size-4 ${isDetecting ? "animate-spin" : ""}`} />
                      Detect models
                    </Button>
                  )}

                {selectedTabSummary.has_api_key && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={providerConfig.isPending}
                    onClick={() =>
                      providerConfig.mutate({
                        provider: selectedTabSummary.id,
                        clear_key: true,
                      })
                    }
                  >
                    <Trash2 className="size-4" />
                    Remove key
                  </Button>
                )}
              </div>

              {providerConfig.error && (
                <p role="alert" className="text-xs text-critical">
                  {providerConfig.error.message}
                </p>
              )}
              {providerConfig.isSuccess && (
                <p role="status" className="text-xs text-success">
                  Provider settings updated on this NVR ({selectedTabSummary.selected_model}).
                </p>
              )}
            </form>
          )
        ) : (
          <div className="mt-6 rounded-lg border border-border bg-background/40 p-4 text-xs text-muted-foreground">
            {status.data?.managed_by_environment
              ? "AI provider configuration is managed by the server environment."
              : "Owner permissions are required to add or remove API keys."}
          </div>
        )}

        <details className="mt-6 text-xs">
          <summary className="cursor-pointer font-semibold text-primary-text">
            Local AI & key storage notes
          </summary>
          <p className="mt-2 leading-relaxed text-muted-foreground">
            Cloud keys stay on this NVR host inside your data directory and are masked in responses. For Ollama, run <code>ollama serve</code> or configure <code>NVR_ASSISTANT_MODEL</code> and <code>NVR_ASSISTANT_URL</code>.
          </p>
        </details>
      </section>
    </div>
  );
}
