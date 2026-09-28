/**
 * EKO 2.8 — estados de cabeceras FC (sin renderer RN).
 * No hay Jest ni Testing Library en mobile/. Este script transpila el view-model
 * real con el TypeScript del paquete y revisa que la sección no agregue pago,
 * PDF ni vencimiento.
 * npm run test:invoices
 */
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../package.json"));
const ts = require("typescript");
const viewSrc = readFileSync(join(here, "../src/invoicesView.ts"), "utf8");
const viewJs = ts.transpileModule(viewSrc, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const viewFile = join(mkdtempSync(join(tmpdir(), "eko-invoices-")), "invoicesView.mjs");
writeFileSync(viewFile, viewJs);
const {
  INVOICE_PUBLIC_KEYS,
  invoiceSectionActions,
  invoiceUiPhase,
  formatInvoiceIssuedAt,
  projectInvoiceHeader,
  projectInvoiceList,
} = await import(pathToFileURL(viewFile).href);

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const sectionSrc = readFileSync(
  join(here, "../src/ui/InvoiceHeadersSection.tsx"),
  "utf8",
);
const apiSrc = readFileSync(join(here, "../src/api.ts"), "utf8");
const homeSrc = readFileSync(join(here, "../src/screens/HomeScreen.tsx"), "utf8");

assert(invoiceUiPhase({
  loading: true,
  transportError: false,
  status: null,
  count: 0,
}) === "loading", "loading");

assert(invoiceUiPhase({
  loading: false,
  transportError: false,
  status: "ok",
  count: 1,
}) === "success", "success");

assert(invoiceUiPhase({
  loading: false,
  transportError: false,
  status: "empty",
  count: 0,
}) === "empty", "empty");

assert(invoiceUiPhase({
  loading: false,
  transportError: false,
  status: "ok",
  count: 0,
}) === "empty", "ok sin filas es vacío");

assert(invoiceUiPhase({
  loading: false,
  transportError: false,
  status: "unavailable",
  count: 0,
}) === "unavailable", "unavailable");

assert(invoiceUiPhase({
  loading: false,
  transportError: false,
  status: "error",
  count: 0,
}) === "unavailable", "error se muestra como no disponible");

assert(invoiceUiPhase({
  loading: false,
  transportError: true,
  status: "ok",
  count: 2,
}) === "unavailable", "error de transporte");

assert(invoiceUiPhase({
  loading: true,
  transportError: true,
  status: "error",
  count: 0,
}) === "loading", "loading gana sobre el error previo");

const projected = projectInvoiceHeader({
  invoice_number: "0001-1",
  full_type: "FC A",
  amount: "10.00",
  issued_at: "2026-09-01T00:00:00+00:00",
  status: "Pendiente",
  due_date: "2026-09-10",
  period: "2026-09",
  currency: "ARS",
  pdf: "http://no",
  client_number: "200",
  account_number: "200",
  invoice_id: 99,
  id: 99,
});
assert(projected, "proyecta cabecera");
assert(
  JSON.stringify(Object.keys(projected).sort()) ===
    JSON.stringify([...INVOICE_PUBLIC_KEYS].sort()),
  "solo campos públicos",
);
assert(!("due_date" in projected), "sin vencimiento");
assert(!("client_number" in projected), "sin cuenta");
assert(projected.invoice_number === "0001-1", "número");
assert(projected.amount === "10.00", "importe");
assert(projected.status === "Pendiente", "estado");

assert(projectInvoiceHeader({ due_date: "x" }) === null, "sin número no se muestra");
assert(projectInvoiceList({ invoices: [] }).length === 0, "lista no array");
assert(projectInvoiceList([projected, { client_number: "1" }]).length === 1, "descarta basura");

assert(invoiceSectionActions().length === 0, "sin acciones comerciales");

for (const forbidden of [
  "vencimiento",
  "due_date",
  "Pagar",
  "PDF",
  "talón",
  "Talón",
  "currency",
  "period",
]) {
  assert(!sectionSrc.includes(forbidden), `sección no debe mencionar ${forbidden}`);
}
assert(sectionSrc.includes("Cargando facturas"), "estado loading");
assert(sectionSrc.includes("No encontramos facturas recientes"), "estado vacío");
assert(sectionSrc.includes("No pudimos consultar tus facturas ahora"), "estado unavailable");
assert(sectionSrc.includes("Factura "), "muestra número");
assert(sectionSrc.includes("Emitida:"), "muestra fecha de emisión");
assert(sectionSrc.includes("formatInvoiceIssuedAt"), "fecha de emisión de factura");
assert(!sectionSrc.includes("formatTicketWhen"), "no usa el formatter de tickets");
assert(sectionSrc.includes("Estado:"), "muestra estado");
assert(sectionSrc.includes("formatMontoDisplay"), "importe con el formateo existente");
assert(sectionSrc.includes('label="Reintentar"'), "reintento, no un CTA comercial");

const getInvoices = apiSrc.slice(
  apiSrc.indexOf("async getInvoices"),
  apiSrc.indexOf("async getCustomerSummary"),
);
assert(getInvoices.includes('"/api/v1/portal/invoices"'), "path del GET");
assert(!getInvoices.includes("client_number"), "el cliente no manda client_number");
assert(!getInvoices.includes("?"), "sin query de identidad");

assert(homeSrc.includes("<BalanceCard"), "el saldo sigue en el Home");
assert(homeSrc.includes("ovLinks={summary.ovLinks}"), "OV sigue en la tarjeta de saldo");
assert(homeSrc.includes("<InvoiceHeadersSection"), "facturas junto al saldo");
assert(!homeSrc.includes("invoices={summary"), "el saldo no sale de las facturas");

const issuedCases = [
  ["2026-09-01T00:00:00+00:00", "01/09/2026"],
  ["2026-09-15T00:00:00+00:00", "15/09/2026"],
  ["2026-12-31T00:00:00+00:00", "31/12/2026"],
  ["2026-09-01T00:00:00-03:00", "01/09/2026"],
  ["2026-09-01T22:00:00-03:00", "01/09/2026"],
];

for (const [iso, expected] of issuedCases) {
  const got = formatInvoiceIssuedAt(iso);
  assert(got === expected, `issued_at ${iso} → ${got}, se esperaba ${expected}`);
  assert(/^\d{2}\/\d{2}\/\d{4}$/.test(got), "fecha absoluta dd/mm/aaaa");
  assert(!/ayer|hace\s/i.test(got), "no es una fecha relativa");
}

const qaIso = "2026-09-01T00:00:00+00:00";
const localShift = new Date(qaIso);
const localLabel = [
  String(localShift.getDate()).padStart(2, "0"),
  String(localShift.getMonth() + 1).padStart(2, "0"),
  String(localShift.getFullYear()),
].join("/");
if (localLabel !== "01/09/2026") {
  assert(
    formatInvoiceIssuedAt(qaIso) !== localLabel,
    "no debe seguir el día desplazado por la zona local",
  );
}

const child = `
const mod = await import(${JSON.stringify(pathToFileURL(viewFile).href)});
const samples = ${JSON.stringify(issuedCases)};
for (const [iso, expected] of samples) {
  const got = mod.formatInvoiceIssuedAt(iso);
  if (got !== expected) {
    console.error(iso, got, expected);
    process.exit(1);
  }
}
`;
for (const tz of ["UTC", "America/Buenos_Aires", "Pacific/Kiritimati"]) {
  const res = spawnSync(process.execPath, ["--input-type=module", "-e", child], {
    env: { ...process.env, TZ: tz },
    encoding: "utf8",
  });
  assert(res.status === 0, `TZ=${tz} ${res.stderr || res.stdout}`);
}

console.log("verify-invoices: ok");
