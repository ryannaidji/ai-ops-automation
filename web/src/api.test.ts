import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { AiServiceClient, ApiError, signBody, type RoutingDecision } from "./api";

function fakeFetch(status: number, body: unknown, calls: { url: string; init?: RequestInit }[] = []) {
  return async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return new Response(typeof body === "string" ? body : JSON.stringify(body), { status });
  };
}

describe("signBody", () => {
  it("matches the Python/Node HMAC scheme sha256=hex(HMAC(secret, ts.body))", async () => {
    const expected = "sha256=" + createHmac("sha256", "s3cret").update('1700000000.{"a":1}').digest("hex");
    expect(await signBody("s3cret", "1700000000", '{"a":1}')).toBe(expected);
  });
});

describe("AiServiceClient", () => {
  it("submitTicket sends signed raw body and returns typed decision", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const decision: Partial<RoutingDecision> = { ticket_id: "t1", route: "queue" };
    const c = new AiServiceClient("http://svc/", fakeFetch(200, decision, calls));
    const res = await c.submitTicket({ ticket_id: "t1", body: "hi" }, "k", () => 1_700_000_000_000);

    expect(res.route).toBe("queue");
    expect(calls[0]!.url).toBe("http://svc/webhook/ticket");
    const headers = calls[0]!.init!.headers as Record<string, string>;
    expect(headers["X-Timestamp"]).toBe("1700000000");
    expect(headers["X-Signature"]).toBe(await signBody("k", "1700000000", calls[0]!.init!.body as string));
  });

  it("listTickets hits GET /tickets", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const c = new AiServiceClient("http://svc", fakeFetch(200, [], calls));
    expect(await c.listTickets(5)).toEqual([]);
    expect(calls[0]!.url).toBe("http://svc/tickets?limit=5");
  });

  it("throws ApiError with status on non-2xx", async () => {
    const c = new AiServiceClient("http://svc", fakeFetch(401, '{"detail":"invalid signature"}'));
    await expect(c.classify("x")).rejects.toBeInstanceOf(ApiError);
    await expect(c.classify("x")).rejects.toMatchObject({ status: 401 });
  });
});
