/**
 * H-APP-2 — presentación de reclamos: src/ticketView.ts, el mismo archivo que usa la app.
 * Se transpila en memoria con `typescript` (devDependency).
 * npm run test:tickets
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ts = require("typescript");

const source = readFileSync(new URL("../src/ticketView.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const view = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);
const {
  ticketStatusLabel,
  isTicketClosed,
  normalizeCategory,
  ticketTitle,
  ticketReference,
  lastMovementTitle,
  timelineEvents,
  eventTitle,
  formatTicketMoment,
} = view;

let n = 0;
const check = (actual, expected, label) => {
  assert.deepEqual(actual, expected, label);
  n += 1;
};

// --- Estados ---
for (const [estado, esperado] of [
  ["Abierto", "Recibido"],
  ["En Revisión", "En revisión"],
  ["Escalado", "En curso"],
  ["Pendiente Cliente", "Esperando tu respuesta"],
  ["Cerrado", "Cerrado"],
  ["  Cerrado  ", "Cerrado"],
  ["Resuelto", "En curso"],
  ["abierto", "En curso"],
  ["", "En curso"],
  [null, "En curso"],
  [undefined, "En curso"],
]) {
  check(ticketStatusLabel(estado), esperado, `estado ${JSON.stringify(estado)}`);
}
check(isTicketClosed("Cerrado"), true, "Cerrado está cerrado");
check(isTicketClosed("Abierto"), false, "Abierto no está cerrado");

// --- Títulos ---
check(normalizeCategory("Móvil  Llamadas"), "movil_llamadas", "normaliza tildes y espacios");
check(normalizeCategory("APN / Datos"), "apn_/_datos", "normaliza la barra como el backend");
check(
  ticketTitle({ titulo: "Sin señal en casa", categoria: "Movil Llamadas" }),
  "Sin señal en casa",
  "manda el titulo del backend",
);
for (const [categoria, esperado] of [
  ["Movil Llamadas", "Llamadas en tu línea móvil"],
  ["movil_datos", "Datos móviles"],
  ["Corte Deuda", "Consulta por corte del servicio"],
  ["Internet Lento", "Internet lento"],
  ["Facturacion Reclamo", "Reclamo de factura"],
  ["Voz", "Llamadas"],
  ["APN / Datos", "Datos móviles"],
  ["Internet", "Internet"],
  ["Fibra", "Internet por fibra"],
  ["Roaming", "Roaming"],
  ["Red / Core", "Problema en la red"],
  ["Canal Abonado", "Reclamo"],
  ["General", "Reclamo"],
  ["TK_INTERNO_XYZ", "Reclamo"],
  ["", "Reclamo"],
]) {
  check(ticketTitle({ categoria }), esperado, `sin titulo, categoría ${JSON.stringify(categoria)}`);
  check(ticketTitle({ titulo: "  ", categoria }), esperado, `titulo vacío, ${JSON.stringify(categoria)}`);
}
check(ticketReference("TK-12"), "Reclamo TK-12", "referencia con ID");
check(ticketReference(""), "Reclamo", "referencia sin ID");

// --- Último movimiento ---
check(
  lastMovementTitle({ ultimo_movimiento: { titulo: "Tu reclamo se cerró", created_at: "x" } }),
  "Tu reclamo se cerró",
  "último movimiento presente",
);
check(lastMovementTitle({ ultimo_movimiento: null }), "", "sin eventos visibles");
check(lastMovementTitle({}), "", "backend previo sin el campo");
check(lastMovementTitle({ ultimo_movimiento: {} }), "", "movimiento sin título");

// --- Línea de tiempo ---
const ev = (id, created_at, titulo = "t") => ({ id, titulo, detalle: "", estado: "", created_at });
const ordered = timelineEvents([
  ev("c", "2026-10-03T10:00:00"),
  ev("a", "2026-10-01T10:00:00"),
  ev("b1", "2026-10-02T10:00:00"),
  ev("b2", "2026-10-02T10:00:00"),
]);
check(ordered.map((e) => e.id), ["a", "b1", "b2", "c"], "de más vieja a más nueva, estable");
check(timelineEvents(null), [], "sin eventos");
const original = [ev("z", "2026-10-05"), ev("y", "2026-10-04")];
timelineEvents(original);
check(original.map((e) => e.id), ["z", "y"], "no muta el arreglo recibido");
check(eventTitle({ titulo: "Recibimos tu reclamo" }), "Recibimos tu reclamo", "título del evento");
check(eventTitle({ titulo: "" }), "Actualización", "evento sin título");

// --- Fechas ---
check(formatTicketMoment(""), "", "sin fecha");
check(formatTicketMoment("no-es-fecha"), "", "fecha inválida");
assert.match(formatTicketMoment("2026-10-10T14:32:00"), /2026/, "fecha con año");
n += 1;

console.log(`verify-ticket-view: ${n} casos OK`);
