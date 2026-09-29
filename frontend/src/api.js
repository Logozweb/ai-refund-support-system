const j = async (r) => { if (!r.ok) throw new Error((await r.text()) || r.statusText); return r.json(); };
export const api = {
  health: () => fetch("/api/health").then(j),
  llmCheck: () => fetch("/api/llm-check").then(j),
  customers: () => fetch("/api/customers").then(j),
  orders: (email) => fetch("/api/orders?email=" + encodeURIComponent(email)).then(j),
  policy: () => fetch("/api/policy").then(j),
  submit: (body) => fetch("/api/refunds", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  list: () => fetch("/api/refunds").then(j),
  resolve: (id, decision, note) => fetch(`/api/refunds/${id}/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, note }) }).then(j),
};
