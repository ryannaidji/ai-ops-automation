import { AiServiceClient, type TicketRecord } from "./api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const SECRET = import.meta.env.VITE_WEBHOOK_SECRET ?? "dev-secret-change-me";
const client = new AiServiceClient(API);

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;

function cell(text: string, cls?: string): HTMLTableCellElement {
  const td = document.createElement("td");
  td.textContent = text; // textContent, never innerHTML: ticket text is untrusted
  if (cls) td.className = cls;
  return td;
}

export function renderTickets(rows: TicketRecord[], tbody: HTMLElement): void {
  tbody.replaceChildren(
    ...rows.map((t) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(t.ticket_id),
        cell(t.route, `route-${t.route}`),
        cell(t.classification.category),
        cell(t.classification.urgency),
        cell(t.classification.sentiment),
        cell(t.redacted_text.slice(0, 160)),
        cell(t.created_at),
      );
      return tr;
    }),
  );
}

async function refresh(): Promise<void> {
  try {
    renderTickets(await client.listTickets(), $("#tickets"));
    $("#status").textContent = `connected to ${API}`;
  } catch (e) {
    $("#status").textContent = `cannot reach ai-service: ${(e as Error).message}`;
  }
}

$("#ticket-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target as HTMLFormElement;
  const data = new FormData(form);
  const out = $("#result");
  out.textContent = "processing (local LLM, may take a few seconds)...";
  try {
    const decision = await client.submitTicket(
      { ticket_id: `web-${Date.now()}`, subject: String(data.get("subject") ?? ""), body: String(data.get("body") ?? ""), channel: "form" },
      SECRET,
    );
    out.textContent = JSON.stringify(decision, null, 2);
    form.reset();
    await refresh();
  } catch (e) {
    out.textContent = (e as Error).message;
  }
});

$("#refresh").addEventListener("click", () => void refresh());
void refresh();
