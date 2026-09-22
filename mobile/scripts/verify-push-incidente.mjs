/**
 * Verificación push sin deps. Espejo de pushIncidente.ts — mantener alineado.
 * npm run test:push
 *
 * Cubre: incidente (E′4), Eko conversación, ticket (2.3G-M).
 */

function asRecord(raw) {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
  return {};
}

function normalizeIncidenteEvent(raw) {
  const e = String(raw || "").trim().toLowerCase();
  if (e === "declared" || e === "create" || e === "created") return "declared";
  if (e === "updated" || e === "update") return "updated";
  if (e === "resolved" || e === "resolve") return "resolved";
  return "";
}

function normalizeTicketEvent(raw) {
  const e = String(raw || "").trim().toLowerCase();
  const bare = e.startsWith("ticket.") ? e.slice("ticket.".length) : e;
  if (bare === "created" || bare === "create") return "created";
  if (bare === "updated" || bare === "update") return "updated";
  if (bare === "resolved" || bare === "resolve") return "resolved";
  if (bare === "closed" || bare === "close") return "closed";
  return "";
}

function emptyIntent(partial) {
  return {
    refreshConnectivity: false,
    outage_id: "",
    ticket_id: "",
    ...partial,
  };
}

function parseIncidentePush(raw) {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo !== "incidente") return null;
  return {
    tipo: "incidente",
    outage_id: String(data.outage_id || data.outageId || "").trim(),
    event: normalizeIncidenteEvent(data.event),
  };
}

function parseTicketPush(raw) {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo !== "ticket") return null;
  return {
    tipo: "ticket",
    ticket_id: String(data.ticket_id || data.ticketId || "").trim(),
    event: normalizeTicketEvent(data.event),
  };
}

function intentFromPushData(raw) {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();

  const ticket = parseTicketPush(raw);
  if (ticket) {
    return emptyIntent({
      tab: "activity",
      ticket_id: ticket.ticket_id,
    });
  }

  const convId = String(data.conversacion_id || "").trim();
  if (tipo === "mensaje_agente" || convId) {
    return emptyIntent({ tab: "eko" });
  }

  const incidente = parseIncidentePush(raw);
  if (incidente) {
    return emptyIntent({
      tab: "home",
      refreshConnectivity: true,
      outage_id: incidente.outage_id,
    });
  }

  return emptyIntent({ tab: "home" });
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

// --- incidente (regresión) ---
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
assert(i.ticket_id === "", "incidente sin ticket_id");

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
assert(eko.ticket_id === "", "eko sin ticket_id");

const cold = intentFromPushData({
  tipo: "incidente",
  outage_id: "99",
  event: "updated",
  title: "Ignorar",
  body: "No verdad",
});
assert(cold.outage_id === "99" && cold.tab === "home", "cold/parse sin title");

// --- ticket (2.3G-M) ---
const tp = parseTicketPush({
  tipo: "ticket",
  ticket_id: "TK-1",
  event: "created",
});
assert(tp && tp.tipo === "ticket", "ticket tipo");
assert(tp.ticket_id === "TK-1", "ticket_id");
assert(tp.event === "created", "ticket event created");

for (const event of ["created", "updated", "resolved", "closed"]) {
  const ti = intentFromPushData({
    tipo: "ticket",
    ticket_id: "TK-9",
    event,
  });
  assert(ti.tab === "activity", `ticket ${event} → activity`);
  assert(ti.ticket_id === "TK-9", `ticket ${event} id`);
  assert(!ti.refreshConnectivity, `ticket ${event} no connectivity`);
  assert(ti.outage_id === "", `ticket ${event} no outage`);
}

assert(
  parseTicketPush({ tipo: "ticket", ticket_id: "A", event: "ticket.resolved" })
    .event === "resolved",
  "ticket.resolved bare",
);

const missingId = intentFromPushData({
  tipo: "ticket",
  event: "updated",
});
assert(missingId.tab === "activity", "missing ticket_id → activity");
assert(missingId.ticket_id === "", "missing ticket_id empty");

const malformed = intentFromPushData({
  tipo: "ticket",
  ticket_id: "   ",
  event: "created",
});
assert(malformed.tab === "activity" && malformed.ticket_id === "", "malformed id");

const ticketCamel = intentFromPushData({
  tipo: "ticket",
  ticketId: "CAMEL-1",
  event: "updated",
});
assert(ticketCamel.ticket_id === "CAMEL-1", "ticketId camelCase");

// ticket gana sobre conversacion_id colateral
const ticketWins = intentFromPushData({
  tipo: "ticket",
  ticket_id: "TK-WIN",
  event: "created",
  conversacion_id: "should-ignore",
});
assert(ticketWins.tab === "activity" && ticketWins.ticket_id === "TK-WIN", "ticket > conv");

// incidente no se confunde con ticket
assert(parseTicketPush({ tipo: "incidente", outage_id: "1" }) === null, "no ticket from incidente");
assert(parseIncidentePush({ tipo: "ticket", ticket_id: "1" }) === null, "no incidente from ticket");

// title/body no son autoridad
const ticketIgnoreBody = intentFromPushData({
  tipo: "ticket",
  ticket_id: "TK-SAFE",
  event: "updated",
  title: "interno",
  body: "nota operador",
  detalle: "secreto",
});
assert(
  ticketIgnoreBody.tab === "activity" && ticketIgnoreBody.ticket_id === "TK-SAFE",
  "ticket ignora title/body",
);

console.log("verify-push-incidente: OK (incidente + eko + ticket)");
