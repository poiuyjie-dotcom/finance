const BASE = "/api/v1";

async function req(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      msg = (await r.json()).detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}

export const api = {
  listTasks: () => req("GET", "/tasks"),
  getTask: (id) => req("GET", `/tasks/${id}`),
  parseNl: (nl) => req("POST", "/tasks/parse-nl", { nl_query: nl }),
  createTask: (rule) => req("POST", "/tasks", { rule }),
  updateRule: (id, rule, reason) =>
    req("PUT", `/tasks/${id}/rule`, {
      updated_rule: rule,
      change_reason: reason,
    }),
  versions: (id) => req("GET", `/tasks/${id}/versions`),
  rollback: (id, v) => req("POST", `/tasks/${id}/rollback/${v}`),
  evaluateNow: (id) => req("POST", `/tasks/${id}/evaluate-now`),
  setStatus: (id, action) => req("POST", `/tasks/${id}/status`, { action }),
  deleteTask: (id) => req("DELETE", `/tasks/${id}`),
  resolveConflict: (id, payload) =>
    req("POST", `/tasks/${id}/resolve`, payload),
  health: () => req("GET", "/datasources/health"),
  faultInject: (mode) => req("POST", "/simulator/fault-inject", { mode }),
  complianceTest: (text) =>
    req("POST", `/simulator/compliance-test?text=${encodeURIComponent(text)}`),
  getSettings: () => req("GET", "/settings"),
  updateKeys: (payload) => req("POST", "/settings/keys", payload),
  testConnections: () => req("POST", "/settings/test"),
};
