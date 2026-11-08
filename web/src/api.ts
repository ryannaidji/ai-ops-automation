// Typed client for ai-service. Types mirror services/ai-service/app/models.py.

export type Category = "billing" | "technical" | "account" | "shipping" | "feedback" | "other";
export type Urgency = "low" | "medium" | "high";
export type Sentiment = "negative" | "neutral" | "positive";
export type Route = "escalate" | "queue" | "auto_reply";

export interface Classification { category: Category; urgency: Urgency; sentiment: Sentiment }
export interface Source { file: string; score: number | null; snippet: string }
export interface RedactionResult { redacted: string; entities: { type: string; start: number; end: number }[]; counts: Record<string, number> }
export interface Answer { answer: string; sources: Source[] }
export interface TicketEvent { ticket_id: string; subject?: string; body: string; channel?: "email" | "chat" | "form" | "api" }
export interface RoutingDecision {
  ticket_id: string;
  route: Route;
  reason: string;
  classification: Classification;
  redacted_text: string;
  pii_counts: Record<string, number>;
  suggested_reply: string | null;
  sources: Source[];
  request_id: string;
}
export interface TicketRecord extends RoutingDecision { created_at: string }

export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    super(`ai-service returned ${status}: ${body.slice(0, 200)}`);
  }
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** HMAC-SHA256 over `${timestamp}.${body}` using WebCrypto (browser + Node 18+). */
export async function signBody(secret: string, timestamp: string, body: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`${timestamp}.${body}`));
  return "sha256=" + Array.from(new Uint8Array(mac), (b) => b.toString(16).padStart(2, "0")).join("");
}

export class AiServiceClient {
  constructor(
    private baseUrl: string,
    private fetchFn: FetchLike = (i, init) => fetch(i, init),
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await this.fetchFn(`${this.baseUrl}${path}`, init);
    const text = await res.text();
    if (!res.ok) throw new ApiError(res.status, text);
    return JSON.parse(text) as T;
  }

  private post<T>(path: string, payload: unknown, headers: Record<string, string> = {}): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: typeof payload === "string" ? payload : JSON.stringify(payload),
    });
  }

  health() { return this.request<{ status: string; model: string }>("/health"); }
  classify(text: string) { return this.post<Classification>("/classify", { text }); }
  redact(text: string) { return this.post<RedactionResult>("/redact", { text }); }
  answer(question: string, topK = 3) { return this.post<Answer>("/answer", { question, top_k: topK }); }

  listTickets(limit = 100): Promise<TicketRecord[]> {
    return this.request<TicketRecord[]>(`/tickets?limit=${encodeURIComponent(limit)}`);
  }

  async submitTicket(event: TicketEvent, secret: string, now: () => number = Date.now): Promise<RoutingDecision> {
    const body = JSON.stringify(event);
    const ts = String(Math.floor(now() / 1000));
    const sig = await signBody(secret, ts, body);
    return this.post<RoutingDecision>("/webhook/ticket", body, { "X-Timestamp": ts, "X-Signature": sig });
  }
}
