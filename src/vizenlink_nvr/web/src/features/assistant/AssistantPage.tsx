import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowUp,
  ArrowUpRight,
  Bot,
  Camera,
  Cctv,
  CheckCircle2,
  Footprints,
  History,
  KeyRound,
  Loader2,
  MessageSquare,
  Moon,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  Video,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { cn } from "cn";

interface ToolResult {
  tool_name: string;
  status: string;
  summary: string;
  camera_serial?: string | null;
  camera_name?: string | null;
  snapshot_url?: string | null;
  ir_cut_filter?: string | null;
  day_night_now?: string | null;
  night_vision_type?: string | null;
  brightness?: number | null;
  contrast?: number | null;
  wdr_mode?: string | null;
}

interface Reply {
  message: string;
  mode: string;
  actions: { label: string; href: string }[];
  tool_results?: ToolResult[];
  checked_at: string;
}

interface Exchange {
  question: string;
  reply?: Reply;
  error?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  exchanges: Exchange[];
}

interface StoredAssistantState {
  activeId: string | null;
  conversations: Conversation[];
  useModel: boolean | null;
}

const MAX_CONVERSATIONS = 50;
const STORE_EVENT = "vizenlink-assistant-store-updated";

function assistantStorageKey(userId?: number | string | null): string {
  return `vizenlink_assistant_conversations_v1_${userId ?? "guest"}`;
}

function createConversationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function makeConversationTitle(question: string): string {
  const clean = question.trim().replace(/\s+/g, " ");
  if (clean.length <= 60) return clean;
  return `${clean.slice(0, 57)}…`;
}

function readAssistantStore(key: string): StoredAssistantState {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { activeId: null, conversations: [], useModel: null };
    const parsed = JSON.parse(raw) as Partial<StoredAssistantState>;
    const conversations = Array.isArray(parsed.conversations)
      ? parsed.conversations.filter(
          (c): c is Conversation =>
            Boolean(c) &&
            typeof c.id === "string" &&
            typeof c.title === "string" &&
            typeof c.created_at === "string" &&
            typeof c.updated_at === "string" &&
            Array.isArray(c.exchanges),
        )
      : [];
    const activeId =
      typeof parsed.activeId === "string" && conversations.some((c) => c.id === parsed.activeId)
        ? parsed.activeId
        : null;
    const useModel = typeof parsed.useModel === "boolean" ? parsed.useModel : null;
    return { activeId, conversations, useModel };
  } catch {
    return { activeId: null, conversations: [], useModel: null };
  }
}

function writeAssistantStore(key: string, next: StoredAssistantState): void {
  try {
    localStorage.setItem(key, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(STORE_EVENT, { detail: key }));
  } catch {
    // Ignore storage quota / privacy mode failures; in-memory state still works.
  }
}

function formatConversationTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface ProviderSummary {
  id: "openai" | "gemini" | "claude" | "ollama";
  name: string;
  models: string[];
  selected_model: string | null;
  has_api_key: boolean;
  api_key_masked: string | null;
  requires_key: boolean;
  active: boolean;
}

interface ModelStatus {
  model_configured: boolean;
  model: string | null;
  managed_by_environment?: boolean;
  active_provider?: string;
  providers?: ProviderSummary[];
}

const PROVIDER_SHORT_LABEL: Record<string, string> = {
  openai: "ChatGPT",
  gemini: "Gemini",
  claude: "Claude",
  ollama: "Local AI",
};

const PROMPTS = [
  {
    title: "Check my cameras",
    prompt: "Camera status",
    detail: "Connections and recording status",
    icon: Cctv,
  },
  {
    title: "Find a person event",
    prompt: "Find person events today",
    detail: "Search camera detections",
    icon: Footprints,
  },
  {
    title: "Review recording",
    prompt: "Are my cameras recording?",
    detail: "Inspect recent footage health",
    icon: Video,
  },
  {
    title: "Find camera issues",
    prompt: "Which cameras are offline?",
    detail: "Spot what needs attention",
    icon: ShieldCheck,
  },
];

const CAMERA_TOOL_PROMPTS = [
  {
    label: "Cafeteria → Night IR + Preview",
    prompt: "Set Cafeteria & Lounge to night mode and show me the preview",
    icon: Moon,
  },
  {
    label: "Lobby → Day Colour + Preview",
    prompt: "Set Main Lobby Entrance to day mode and show me the preview",
    icon: Sun,
  },
  {
    label: "Parking → Color Night + Preview",
    prompt: "Set North Parking Lot to full color night mode and show me the preview",
    icon: Sparkles,
  },
  {
    label: "Server Room → Snapshot Preview",
    prompt: "Show preview of Server Room Aisle 1",
    icon: Camera,
  },
];

function renderInlineMarkdown(text: string) {
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={idx} className="rounded bg-muted px-1 text-xs">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function formatVisionMode(tool: ToolResult): string {
  const ir = (tool.ir_cut_filter || "").toLowerCase();
  const vision = (tool.night_vision_type || "").toLowerCase();
  if (ir === "night" || ir === "off") {
    return vision.includes("color") || vision.includes("white")
      ? "Night · Full Color"
      : "Night · IR B&W";
  }
  if (ir === "day" || ir === "on") return "Day · Colour";
  if (ir === "auto") return `Auto (${tool.day_night_now || "Day"})`;
  return tool.day_night_now ? `Active · ${tool.day_night_now}` : "Live camera";
}

function isNightResult(tool: ToolResult): boolean {
  const ir = (tool.ir_cut_filter || "").toLowerCase();
  const current = (tool.day_night_now || "").toLowerCase();
  return ir === "night" || ir === "off" || current === "night";
}

export function AssistantPage() {
  const user = useCurrentUser();
  const storageKey = assistantStorageKey(user?.id);

  const [input, setInput] = useState("");
  const [store, setStore] = useState<StoredAssistantState>(() => readAssistantStore(storageKey));
  const [useModel, setUseModel] = useState<boolean>(() => readAssistantStore(storageKey).useModel ?? false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [previewTick, setPreviewTick] = useState(0);
  const [failedSnapshots, setFailedSnapshots] = useState<Record<string, boolean>>({});

  const tail = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const status = useQuery({
    queryKey: ["assistant", "status"],
    queryFn: () => apiFetch<ModelStatus>("/api/v1/assistant/status"),
    staleTime: 30000,
  });

  const activeProviderSummary = useMemo(
    () =>
      status.data?.providers?.find(
        (p) => p.active || p.id === status.data?.active_provider,
      ),
    [status.data],
  );

  // Sync saved conversations & mode when the user account resolves or changes
  useEffect(() => {
    const loaded = readAssistantStore(storageKey);
    setStore(loaded);
    setUseModel(loaded.useModel ?? Boolean(status.data?.model_configured));
    setHistoryOpen(false);
  }, [storageKey]);

  // Listen for background in-flight completions if the component remounted
  useEffect(() => {
    const onStoreUpdated = (event: Event) => {
      const custom = event as CustomEvent<string>;
      if (custom.detail === storageKey && mountedRef.current) {
        setStore(readAssistantStore(storageKey));
      }
    };
    window.addEventListener(STORE_EVENT, onStoreUpdated);
    return () => window.removeEventListener(STORE_EVENT, onStoreUpdated);
  }, [storageKey]);

  useEffect(() => {
    if (status.data?.model_configured && store.useModel === null) {
      setUseModel(true);
    }
  }, [status.data?.model_configured, store.useModel]);

  const activeConversation = useMemo(
    () => store.conversations.find((c) => c.id === store.activeId) ?? null,
    [store.conversations, store.activeId],
  );
  const exchanges = activeConversation?.exchanges ?? [];

  useEffect(() => {
    if (exchanges.length > 0) {
      tail.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [exchanges.length, store.activeId]);

  const commitStore = (updater: (prev: StoredAssistantState) => StoredAssistantState) => {
    const current = readAssistantStore(storageKey);
    const next = updater(current);
    writeAssistantStore(storageKey, next);
    if (mountedRef.current) {
      setStore(next);
    }
    return next;
  };

  const handleModeChange = (nextUseModel: boolean) => {
    setUseModel(nextUseModel);
    commitStore((prev) => ({ ...prev, useModel: nextUseModel }));
  };

  const handleNewChat = () => {
    commitStore((prev) => ({ ...prev, activeId: null }));
    setHistoryOpen(false);
  };

  const handleSelectConversation = (conversationId: string) => {
    commitStore((prev) => ({ ...prev, activeId: conversationId }));
    setHistoryOpen(false);
  };

  const handleDeleteConversation = (conversationId: string) => {
    commitStore((prev) => {
      const remaining = prev.conversations.filter((c) => c.id !== conversationId);
      const nextActiveId = prev.activeId === conversationId ? null : prev.activeId;
      return { ...prev, activeId: nextActiveId, conversations: remaining };
    });
  };

  const handleClearActiveConversation = () => {
    if (!activeConversation) return;
    handleDeleteConversation(activeConversation.id);
  };

  const chat = useMutation({
    mutationFn: ({ message, use_model }: { message: string; use_model: boolean }) =>
      apiFetch<Reply>("/api/v1/assistant/chat", {
        method: "POST",
        body: { message, use_model },
      }),
  });

  const send = async (question: string) => {
    const message = question.trim();
    if (!message || chat.isPending) return;
    setInput("");
    setHistoryOpen(false);

    const nowIso = new Date().toISOString();
    const currentStore = readAssistantStore(storageKey);
    const existing = currentStore.conversations.find((c) => c.id === currentStore.activeId);
    const targetId = existing ? existing.id : createConversationId();
    let targetExchangeIndex = 0;

    commitStore((prev) => {
      const found = prev.conversations.find((c) => c.id === targetId);
      if (found) {
        const nextExchanges = [...found.exchanges.slice(-29), { question: message }];
        targetExchangeIndex = nextExchanges.length - 1;
        const updatedConv: Conversation = {
          ...found,
          updated_at: nowIso,
          exchanges: nextExchanges,
        };
        const others = prev.conversations.filter((c) => c.id !== targetId);
        return {
          ...prev,
          activeId: targetId,
          conversations: [updatedConv, ...others].slice(0, MAX_CONVERSATIONS),
        };
      }
      targetExchangeIndex = 0;
      const created: Conversation = {
        id: targetId,
        title: makeConversationTitle(message),
        created_at: nowIso,
        updated_at: nowIso,
        exchanges: [{ question: message }],
      };
      return {
        ...prev,
        activeId: targetId,
        conversations: [created, ...prev.conversations].slice(0, MAX_CONVERSATIONS),
      };
    });

    try {
      const reply = await chat.mutateAsync({ message, use_model: useModel });
      commitStore((prev) => ({
        ...prev,
        conversations: prev.conversations.map((conv) =>
          conv.id === targetId
            ? {
                ...conv,
                updated_at: new Date().toISOString(),
                exchanges: conv.exchanges.map((item, i) =>
                  i === targetExchangeIndex ? { ...item, reply } : item,
                ),
              }
            : conv,
        ),
      }));
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : "Couldn't check the recorder. Try again.";
      commitStore((prev) => ({
        ...prev,
        conversations: prev.conversations.map((conv) =>
          conv.id === targetId
            ? {
                ...conv,
                updated_at: new Date().toISOString(),
                exchanges: conv.exchanges.map((item, i) =>
                  i === targetExchangeIndex ? { ...item, error: errMsg } : item,
                ),
              }
            : conv,
        ),
      }));
    }
  };

  const activeModeLabel = status.data?.model_configured
    ? `${PROVIDER_SHORT_LABEL[status.data.active_provider || "ollama"] || "AI"} · ${status.data.model}`
    : "Local AI · not configured";

  return (
    <section
      className="assistant-workspace flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card"
      aria-label="Recorder assistant"
    >
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-4 py-4 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-selected text-primary">
            <Sparkles className="size-4" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">VizenLink Assistant</span>
              <Badge variant="outline" className="text-xs font-normal">
                <Wrench className="size-3" />
                Camera tools ready
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {status.data?.model_configured
                ? `Connected: ${activeProviderSummary?.name ?? status.data.active_provider} (${status.data.model})`
                : "Built-in NVR intelligence & live camera tools"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect
            aria-label="Assistant mode"
            size="sm"
            className="w-auto text-xs"
            disabled={chat.isPending}
            value={useModel ? "model" : "recorder"}
            onChange={(e) => handleModeChange(e.target.value === "model")}
          >
            <option value="recorder">Recorder assistant</option>
            <option value="model" disabled={!status.data?.model_configured}>
              {activeModeLabel}
            </option>
          </NativeSelect>

          {user?.role === "owner" && (
            <Button variant="outline" size="sm" asChild>
              <Link to="/settings/ai">
                <KeyRound className="size-4" />
                AI & API keys
              </Link>
            </Button>
          )}

          <Button
            type="button"
            variant={historyOpen ? "secondary" : "outline"}
            size="sm"
            aria-expanded={historyOpen}
            disabled={store.conversations.length === 0}
            onClick={() => setHistoryOpen((v) => !v)}
          >
            <History className="size-4" />
            Conversations ({store.conversations.length})
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={chat.isPending || !activeConversation}
            onClick={handleNewChat}
          >
            <Plus className="size-4" />
            New chat
          </Button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={chat.isPending || !exchanges.length}
            onClick={handleClearActiveConversation}
          >
            <RotateCcw className="size-4" />
            Clear conversation
          </Button>
        </div>
      </div>

      {historyOpen && store.conversations.length > 0 && (
        <div
          className="border-b border-border bg-muted/20 px-4 py-4 sm:px-6"
          aria-label="Previous conversations"
        >
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                Previous conversations
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-xs"
                onClick={() => setHistoryOpen(false)}
              >
                Hide history
              </Button>
            </div>
            <div className="grid max-h-60 gap-2 overflow-y-auto sm:grid-cols-2">
              {store.conversations.map((conv) => {
                const isActive = conv.id === store.activeId;
                return (
                  <div
                    key={conv.id}
                    className={cn(
                      "flex items-center gap-2 rounded-lg border bg-card p-2 transition-colors",
                      isActive ? "border-primary bg-selected/40" : "border-border hover:border-primary/60",
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 flex-col gap-1 text-left"
                      onClick={() => handleSelectConversation(conv.id)}
                    >
                      <span className="flex items-center gap-2 truncate text-xs font-semibold text-foreground">
                        <MessageSquare className="size-3 shrink-0 text-primary" />
                        <span className="truncate">{conv.title}</span>
                      </span>
                      <span className="text-xs font-normal text-muted-foreground">
                        {conv.exchanges.length} question{conv.exchanges.length === 1 ? "" : "s"} ·{" "}
                        {formatConversationTimestamp(conv.updated_at)}
                      </span>
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete conversation ${conv.title}`}
                      className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDeleteConversation(conv.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div
        className="assistant-conversation flex flex-1 flex-col overflow-y-auto px-4 py-4 sm:px-6"
        aria-live="polite"
        aria-busy={chat.isPending}
      >
        {exchanges.length === 0 ? (
          <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center gap-4">
            <div className="assistant-orb flex size-12 items-center justify-center rounded-xl bg-selected text-primary">
              <Bot className="size-6" />
            </div>

            <div className="text-center">
              <h2 className="text-xl font-semibold">What would you like to inspect or adjust?</h2>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                Ask about camera status and events, or run live camera tools with instant visual preview.
              </p>
            </div>

            <div className="grid w-full gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {PROMPTS.map((p) => (
                <button
                  key={p.prompt}
                  type="button"
                  className="assistant-prompt group rounded-xl border border-border bg-background/40 p-4 text-left transition-colors hover:border-primary hover:bg-selected/40"
                  onClick={() => void send(p.prompt)}
                >
                  <p.icon className="mb-2 size-5 text-primary" />
                  <span className="block text-sm font-semibold">{p.title}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">{p.detail}</span>
                </button>
              ))}
            </div>

            <div className="w-full rounded-xl border border-border bg-background/40 p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                  <Camera className="size-4 text-primary" />
                  Camera tools & live preview
                </span>
                <span className="text-xs text-muted-foreground">
                  Updates camera mode and renders snapshot
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {CAMERA_TOOL_PROMPTS.map((item) => (
                  <Button
                    key={item.prompt}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="text-xs"
                    onClick={() => void send(item.prompt)}
                  >
                    <item.icon className="size-4 text-primary" />
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>

            {store.conversations.length > 0 && (
              <div className="w-full rounded-xl border border-border bg-background/40 p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                    <History className="size-4 text-primary" />
                    Previous conversations
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Click any conversation to resume
                  </span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {store.conversations.slice(0, 6).map((conv) => (
                    <div
                      key={conv.id}
                      className="flex items-center gap-2 rounded-lg border border-border bg-card p-2 transition-colors hover:border-primary/60"
                    >
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 flex-col gap-1 text-left"
                        onClick={() => handleSelectConversation(conv.id)}
                      >
                        <span className="flex items-center gap-2 truncate text-xs font-semibold text-foreground">
                          <MessageSquare className="size-3 shrink-0 text-primary" />
                          <span className="truncate">{conv.title}</span>
                        </span>
                        <span className="text-xs font-normal text-muted-foreground">
                          {conv.exchanges.length} question{conv.exchanges.length === 1 ? "" : "s"} ·{" "}
                          {formatConversationTimestamp(conv.updated_at)}
                        </span>
                      </button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete conversation ${conv.title}`}
                        className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
                        onClick={() => handleDeleteConversation(conv.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
            {exchanges.map((exchange, i) => (
              <div key={i} className="flex flex-col gap-4">
                <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-selected px-4 py-2 text-sm text-selected-foreground">
                  {exchange.question}
                </div>

                <div className="flex items-start gap-2">
                  <span className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-selected text-primary">
                    <Sparkles className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-semibold text-muted-foreground">
                      {exchange.reply?.mode === "ollama"
                        ? "Local AI"
                        : exchange.reply?.mode && exchange.reply.mode !== "recorder"
                          ? PROVIDER_SHORT_LABEL[exchange.reply.mode] || "AI Model"
                          : "Recorder assistant"}
                    </span>

                    {exchange.reply ? (
                      <div className="mt-2 flex flex-col gap-4">
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">
                          {renderInlineMarkdown(exchange.reply.message)}
                        </p>

                        {exchange.reply.tool_results && exchange.reply.tool_results.length > 0 && (
                          <div className="grid gap-4">
                            {exchange.reply.tool_results.map((tool, idx) => {
                              const camLabel = tool.camera_name || tool.camera_serial || "Camera";
                              const night = isNightResult(tool);
                              const cacheBust = encodeURIComponent(
                                `${exchange.reply?.checked_at ?? ""}-${previewTick}`,
                              );
                              const snapKey = `${exchange.reply?.checked_at ?? ""}-${idx}-${previewTick}`;
                              const snapFailed = Boolean(failedSnapshots[snapKey]);
                              return (
                                <div
                                  key={`${tool.camera_serial ?? idx}-${idx}`}
                                  className="overflow-hidden rounded-xl border border-border bg-background/60"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2">
                                    <div className="flex items-center gap-2">
                                      {night ? (
                                        <Moon className="size-4 text-primary" />
                                      ) : (
                                        <Sun className="size-4 text-warning" />
                                      )}
                                      <span className="text-sm font-semibold">{camLabel}</span>
                                      <Badge variant="outline" className="text-xs font-normal">
                                        {formatVisionMode(tool)}
                                      </Badge>
                                    </div>

                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="inline-flex items-center gap-1 rounded-full bg-success-subtle px-2 py-1 text-xs font-semibold text-success">
                                        <CheckCircle2 className="size-3" />
                                        {tool.status === "ok" ? "Tool applied" : tool.status}
                                      </span>
                                      {tool.snapshot_url && (
                                        <Button
                                          type="button"
                                          size="sm"
                                          variant="outline"
                                          className="text-xs"
                                          onClick={() => setPreviewTick((v) => v + 1)}
                                        >
                                          <RefreshCw className="size-4" />
                                          Refresh preview
                                        </Button>
                                      )}
                                      {tool.camera_serial && (
                                        <Button variant="ghost" size="sm" className="text-xs" asChild>
                                          <Link to={`/cameras/${tool.camera_serial}?tab=image`}>
                                            Image settings
                                            <ArrowUpRight className="size-4" />
                                          </Link>
                                        </Button>
                                      )}
                                    </div>
                                  </div>

                                  {tool.snapshot_url && (
                                    <div className="aspect-video w-full overflow-hidden bg-video-bg">
                                      {snapFailed ? (
                                        <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center text-xs text-muted-foreground">
                                          <Camera className="size-6 opacity-60" />
                                          <p>
                                            Couldn&apos;t load live snapshot from {camLabel}. Click Refresh preview to retry.
                                          </p>
                                        </div>
                                      ) : (
                                        <img
                                          key={snapKey}
                                          src={`${tool.snapshot_url}${tool.snapshot_url.includes("?") ? "&" : "?"}t=${cacheBust}`}
                                          alt={`Live preview of ${camLabel}`}
                                          className="h-full w-full object-cover"
                                          onError={() =>
                                            setFailedSnapshots((prev) => ({ ...prev, [snapKey]: true }))
                                          }
                                        />
                                      )}
                                    </div>
                                  )}

                                  <div className="flex flex-wrap items-center justify-between gap-2 p-4">
                                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                      <span>{tool.summary}</span>
                                      {typeof tool.brightness === "number" && (
                                        <Badge variant="outline" className="text-xs font-normal">
                                          Brightness {tool.brightness}
                                        </Badge>
                                      )}
                                      {typeof tool.contrast === "number" && (
                                        <Badge variant="outline" className="text-xs font-normal">
                                          Contrast {tool.contrast}
                                        </Badge>
                                      )}
                                      {tool.wdr_mode && (
                                        <Badge variant="outline" className="text-xs font-normal">
                                          WDR {tool.wdr_mode}
                                        </Badge>
                                      )}
                                    </div>

                                    <div className="flex flex-wrap gap-1">
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="text-xs"
                                        disabled={chat.isPending}
                                        onClick={() =>
                                          void send(
                                            `Set ${camLabel} to auto mode and show me the preview`,
                                          )
                                        }
                                      >
                                        Auto
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="text-xs"
                                        disabled={chat.isPending}
                                        onClick={() =>
                                          void send(
                                            `Set ${camLabel} to day mode and show me the preview`,
                                          )
                                        }
                                      >
                                        <Sun className="size-4" />
                                        Day
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="text-xs"
                                        disabled={chat.isPending}
                                        onClick={() =>
                                          void send(
                                            `Set ${camLabel} to night mode and show me the preview`,
                                          )
                                        }
                                      >
                                        <Moon className="size-4" />
                                        Night IR
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        className="text-xs"
                                        disabled={chat.isPending}
                                        onClick={() =>
                                          void send(
                                            `Set ${camLabel} to color night mode and show me the preview`,
                                          )
                                        }
                                      >
                                        <Sparkles className="size-4" />
                                        Color night
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {exchange.reply.actions.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {exchange.reply.actions.map((a) => (
                              <Button key={a.href} variant="outline" size="sm" asChild>
                                <Link to={a.href}>
                                  {a.label}
                                  <ArrowUpRight className="size-4" />
                                </Link>
                              </Button>
                            ))}
                          </div>
                        )}

                        <p className="text-xs text-muted-foreground">
                          Checked {new Date(exchange.reply.checked_at).toLocaleTimeString()}
                        </p>
                      </div>
                    ) : exchange.error ? (
                      <div role="alert">
                        <p className="mt-2 text-sm text-critical">{exchange.error}</p>
                        <Button
                          className="mt-2"
                          variant="outline"
                          size="sm"
                          onClick={() => void send(exchange.question)}
                        >
                          Try this question again
                        </Button>
                      </div>
                    ) : (
                      <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="size-4 animate-spin" />
                        {useModel
                          ? "Asking your connected model…"
                          : "Checking recorder & running tools…"}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        <div ref={tail} />
      </div>

      <div className="border-t border-border px-4 py-4 sm:px-6">
        <div className="mx-auto w-full max-w-4xl">
          <form
            className="flex items-end gap-2 rounded-xl border border-border bg-background p-2 focus-within:ring-2 focus-within:ring-primary"
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
          >
            <textarea
              aria-label="Ask the recorder assistant"
              placeholder="Try: “Set Cafeteria camera to night mode and show me the preview” or ask about events…"
              rows={1}
              maxLength={2000}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              className="max-h-32 min-h-10 min-w-0 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || chat.isPending}
              aria-label="Send question"
            >
              {chat.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ArrowUp className="size-4" />
              )}
            </Button>
          </form>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>Camera tools verify permissions · Preview updates live</span>
            <div className="flex flex-wrap gap-4">
              <Link to="/search" className="hover:text-primary-text">
                Search footage
              </Link>
              <Link to="/live" className="hover:text-primary-text">
                Live view
              </Link>
              <Link to="/cameras" className="hover:text-primary-text">
                Cameras
              </Link>
              <Link to="/events" className="hover:text-primary-text">
                Alerts
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
