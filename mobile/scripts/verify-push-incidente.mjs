/**
 * Verificación E′4 sin deps. Espejo de pushIncidente.ts — mantener alineado.
 * npm run test:push
 */
function asRecord(raw) {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
  return {};
}

function normalizeEvent(raw) {
  const e = String(raw || "").trim().toLowerCase();
  if (e === "declared" || e === "create" || e === "created") return "declared";
  if (e === "updated" || e === "update") return "updated";
  if (e === "resolved" || e === "resolve") return "resolved";
  return "";
}

function parseIncidentePush(raw) {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo !== "incidente") return null;
  return {
    tipo: "incidente",
    outage_id: String(data.outage_id || data.outageId || "").trim(),
    event: normalizeEvent(data.event),
  };
}

function intentFromPushData(raw) {
  const data = asRecord(raw);
  const convId = String(data.conversacion_id || "").trim();
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo === "mensaje_agente" || convId) {
    return { tab: "eko", refreshConnectivity: false, outage_id: "" };
  }
  const incidente = parseIncidentePush(raw);
  if (incidente) {
    return {
      tab: "home",
      refreshConnectivity: true,
      outage_id: incidente.outage_id,
    };
  }
  return { tab: "home", refreshConnectivity: false, outage_id: "" };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const p = parseIncidentePush({
  tipo: "incidente",
  outage_id: "123",
  event: "updated",
});
assert(p && p.tipo === "incidente", "tipo");
assert(p.outage_id === "123", "outage_id");
assert(p.event === "updated", "event");

const i = intentFromPushData({
  tipo: "incidente",
  outage_id: "123",
  event: "updated",
});
assert(i.tab === "home", "tab");
assert(i.refreshConnectivity === true, "refresh");
assert(i.outage_id === "123", "route id");

const a = intentFromPushData({
  tipo: "incidente",
  outage_id: "123",
  event: "updated",
});
const b = intentFromPushData({
  tipo: "incidente",
  outage_id: "123",
  event: "updated",
});
assert(a.outage_id === b.outage_id && a.tab === b.tab, "no duplicar destino");

const x = intentFromPushData({
  tipo: "incidente",
  outage_id: "123",
  event: "updated",
});
const y = intentFromPushData({
  tipo: "incidente",
  outage_id: "456",
  event: "updated",
});
assert(x.outage_id === "123" && y.outage_id === "456", "ids distintos");

for (const event of ["declared", "resolved"]) {
  const z = intentFromPushData({
    tipo: "incidente",
    outage_id: "abc",
    event,
  });
  assert(z.tab === "home" && z.refreshConnectivity, event);
}

const eko = intentFromPushData({
  tipo: "mensaje_agente",
  conversacion_id: "c1",
});
assert(eko.tab === "eko" && !eko.refreshConnectivity, "eko");

const cold = intentFromPushData({
  tipo: "incidente",
  outage_id: "99",
  event: "updated",
  title: "Ignorar",
  body: "No verdad",
});
assert(cold.outage_id === "99" && cold.tab === "home", "cold/parse sin title");

console.log("verify-push-incidente: OK");
