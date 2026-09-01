/** Contrato de 4 endpoints críticos del api-client (URL, método, forma JSON). */

import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";

import { api } from "./api-client";

type FetchCall = { url: string; init: RequestInit };

let last: FetchCall | undefined;
let jsonBody: unknown = {};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

beforeEach(() => {
  last = undefined;
  jsonBody = {};
  mock.method(
    globalThis,
    "fetch",
    async (input: RequestInfo | URL, init?: RequestInit) => {
      last = { url: fetchUrl(input), init: init ?? {} };
      return jsonResponse(jsonBody);
    },
  );
});

afterEach(() => {
  mock.restoreAll();
});

function assertLast(path: string, method = "GET") {
  assert.ok(last, "fetch no fue llamado");
  assert.equal(new URL(last.url, "http://contrato.local").pathname, path);
  assert.equal((last.init.method || "GET").toUpperCase(), method);
  assert.equal(last.init.credentials, "include");
}

function assertKeys(obj: object, keys: string[]) {
  for (const key of keys) {
    assert.ok(key in obj, `falta clave de contrato: ${key}`);
  }
}

test("login POST /api/login y LoginResponse", async () => {
  jsonBody = {
    token: "t",
    rol: "agente",
    usuario: "ana",
    nombre: "Ana",
    org_slug: "coop-batan",
  };
  const data = await api.login("ana", "x");
  assertLast("/api/login", "POST");
  assert.equal(JSON.parse(String(last?.init.body)).usuario, "ana");
  assertKeys(data, ["token", "rol", "usuario", "nombre"]);
});

test("tickets GET /api/v1/tickets (no /api/tickets)", async () => {
  jsonBody = {
    tenant: "coop-batan",
    tickets: [
      {
        id: "TK-1",
        linea: "2235402690",
        dispositivo: "ONU",
        descripcion_falla: "sin internet",
        origen: "chat",
        estado: "Abierto",
        categoria: "General",
      },
    ],
  };
  const data = await api.tickets({ estado: "Abierto", limit: 20 }, "coop-batan");
  assertLast("/api/v1/tickets");
  assert.ok(!last?.url.includes("/api/tickets?"));
  assert.match(last?.url || "", /[?&]estado=Abierto/);
  assert.match(last?.url || "", /[?&]limit=20/);
  const headers = last?.init.headers as Record<string, string>;
  assert.equal(headers["X-Tenant-Slug"], "coop-batan");
  assertKeys(data, ["tenant", "tickets"]);
  assert.ok(Array.isArray(data.tickets));
  assertKeys(data.tickets[0], ["id", "linea", "estado"]);
});

test("inbox GET /api/v1/inbox/conversations", async () => {
  jsonBody = {
    tenant: "coop-batan",
    conversaciones: [
      {
        id: "c1",
        canal: "whatsapp",
        wa_id: "",
        telefono: "2235402690",
        abonado_id: "",
        estado: "bot",
        agente_id: "",
        session_id: "",
        servicio_detectado: "",
        ticket_id: "",
        created_at: "2026-09-01T00:00:00Z",
        updated_at: "2026-09-01T00:00:00Z",
      },
    ],
  };
  const data = await api.inboxConversations({ estado: "bot", limit: 50 });
  assertLast("/api/v1/inbox/conversations");
  assert.match(last?.url || "", /[?&]estado=bot/);
  assertKeys(data, ["tenant", "conversaciones"]);
  assertKeys(data.conversaciones[0], ["id", "canal", "estado"]);
});

test("portalSession POST /api/v1/portal/session", async () => {
  jsonBody = {
    portal_token: "pt",
    org_slug: "coop-batan",
    conversacion: {
      id: "c1",
      canal: "portal",
      wa_id: "",
      telefono: "",
      abonado_id: "",
      estado: "bot",
      agente_id: "",
      session_id: "",
      servicio_detectado: "",
      ticket_id: "",
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    },
    mensajes: [],
    abonado_identificado: false,
  };
  const data = await api.portalSession({ dni: "30111222", org_slug: "coop-batan" });
  assertLast("/api/v1/portal/session", "POST");
  assert.equal(JSON.parse(String(last?.init.body)).dni, "30111222");
  assertKeys(data, [
    "portal_token",
    "org_slug",
    "conversacion",
    "mensajes",
    "abonado_identificado",
  ]);
});
