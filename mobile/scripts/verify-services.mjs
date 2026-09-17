/**
 * Verificación Milestone G1 — catálogo tipado (sin deps RN).
 * npm run test:services
 */
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const CANONICAL = new Set(["internet", "tv", "movil", "telefonia", "other"]);

const CODE_MAP = {
  INTFO: "internet",
  INTBA: "internet",
  INTINA: "internet",
  SENSA: "tv",
  OTT: "tv",
  IPTV: "tv",
  IMOWI: "movil",
  CEL: "movil",
};

function mapCode(code) {
  const c = String(code || "").trim().toUpperCase();
  if (CODE_MAP[c]) return CODE_MAP[c];
  return "other";
}

function normalizeItem(raw) {
  const id = String(raw?.id || "").trim();
  if (!id) return null;
  const type = CANONICAL.has(raw?.type) ? raw.type : mapCode(raw?.service_type_code);
  const productRaw = raw?.product;
  const product =
    productRaw === null || productRaw === undefined || String(productRaw).trim() === ""
      ? null
      : String(productRaw).trim();
  return {
    id,
    type,
    label: String(raw?.label || "").trim(),
    product,
    active: Boolean(raw?.active),
  };
}

function parseServicesResponse(body) {
  const services = Array.isArray(body?.services) ? body.services : [];
  return {
    status: body?.status === "unavailable" ? "unavailable" : "ok",
    services: services.map(normalizeItem).filter(Boolean),
  };
}

function ctaFor(type) {
  if (type === "internet") return "connectivity+wifi";
  return "eko";
}

const WIFI_CHANGE_PROMPT =
  "Quiero cambiar la contraseña o el nombre de mi Wi-Fi.";

function internetQuickActions() {
  return [
    { label: "Ver estado", kind: "connectivity" },
    { label: "Cambiar Wi-Fi", kind: "eko", text: WIFI_CHANGE_PROMPT },
  ];
}

// --- mapping ---
assert(mapCode("INTFO") === "internet", "INTFO");
assert(mapCode("SENSA") === "tv", "SENSA");
assert(mapCode("IMOWI") === "movil", "IMOWI");
assert(mapCode("XYZ") === "other", "unknown→other");

// --- DTO: no inventar product ---
{
  const item = normalizeItem({
    id: "1",
    type: "internet",
    label: "Internet",
    product: "",
    active: true,
  });
  assert(item.product === null, "product vacío → null");
}

// --- no usar label como id ---
{
  const a = normalizeItem({ id: "svc-1", type: "tv", label: "Sensa", product: "Sensa", active: true });
  const b = normalizeItem({ id: "svc-1", type: "tv", label: "Otro texto", product: "Sensa", active: true });
  assert(a.id === b.id, "id estable");
}

// --- multi + CTAs ---
{
  const res = parseServicesResponse({
    status: "ok",
    services: [
      { id: "i", type: "internet", label: "Fibra", product: "300M", active: true },
      { id: "t", type: "tv", label: "TV", product: "Sensa", active: true },
      { id: "m", type: "movil", label: "Móvil", product: null, active: true },
      { id: "o", type: "other", label: "Pack", product: null, active: false },
    ],
  });
  assert(res.services.length === 4, "cuatro");
  assert(ctaFor(res.services[0].type) === "connectivity+wifi", "internet→connectivity+wifi");
  assert(ctaFor(res.services[1].type) === "eko", "tv→eko");
  assert(ctaFor(res.services[2].type) === "eko", "movil→eko");
  assert(ctaFor(res.services[3].type) === "eko", "other→eko");
  const wifiCtas = internetQuickActions();
  assert(wifiCtas[1].label === "Cambiar Wi-Fi", "cta label");
  assert(wifiCtas[1].text === WIFI_CHANGE_PROMPT, "cta pendingChatText");
  assert(wifiCtas[1].kind === "eko", "cta navega a Eko");
}

// --- omitir sin id ---
{
  const res = parseServicesResponse({
    status: "ok",
    services: [{ id: "", type: "internet", label: "x", product: null, active: true }],
  });
  assert(res.services.length === 0, "sin id");
}

// --- empty / unavailable / error states (contrato UI) ---
{
  const empty = parseServicesResponse({ status: "ok", services: [] });
  assert(empty.services.length === 0 && empty.status === "ok", "empty");
  const unav = parseServicesResponse({ status: "unavailable", services: [] });
  assert(unav.status === "unavailable", "unavailable");
}

// --- no estado operativo inventado en catálogo ---
{
  const item = normalizeItem({
    id: "tv1",
    type: "tv",
    label: "Sensa",
    product: "Sensa",
    active: true,
  });
  assert(!("operational" in item), "no operational");
  assert(!("online" in item), "no online");
  assert(item.active === true, "active admin");
}

console.log("verify-services: ok");
