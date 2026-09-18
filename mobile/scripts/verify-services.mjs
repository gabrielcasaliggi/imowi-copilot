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
  let line_msisdn = null;
  if (raw?.line_msisdn !== undefined && raw?.line_msisdn !== null) {
    const digits = String(raw.line_msisdn).replace(/\D/g, "");
    line_msisdn = digits.length === 10 ? digits : null;
  }
  return {
    id,
    type,
    label: String(raw?.label || "").trim(),
    product,
    active: Boolean(raw?.active),
    line_msisdn,
  };
}

/** Espejo de maskLineMsisdn en ServicesSection.tsx */
function maskLineMsisdn(line) {
  const digits = String(line || "").replace(/\D/g, "");
  if (digits.length !== 10) return null;
  return `····${digits.slice(-4)}`;
}

/** UI: solo item.line_msisdn contractual; sin fallbacks. */
function lineLabelForDisplay(item) {
  if (item?.type !== "movil") return null;
  const masked = maskLineMsisdn(item.line_msisdn);
  return masked ? `Línea ${masked}` : null;
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

// --- Ver estado: no descartar tap mientras hay consulta en vuelo ---
{
  /** Espejo de pendingSid en useConnectivity.load */
  function makeLoadQueue(fetchFn) {
    let inFlight = false;
    let pending = undefined; // undefined=none; null=reload; string=id
    const calls = [];
    async function load(serviceId) {
      if (inFlight) {
        pending = serviceId === undefined ? null : serviceId;
        return;
      }
      inFlight = true;
      calls.push(serviceId === undefined ? null : serviceId);
      try {
        await fetchFn(serviceId);
      } finally {
        inFlight = false;
        const next = pending;
        if (next !== undefined) {
          pending = undefined;
          await load(next);
        }
      }
    }
    return { load, calls };
  }

  const seen = [];
  const q = makeLoadQueue(async (sid) => {
    seen.push(sid ?? null);
    await new Promise((r) => setTimeout(r, 5));
  });
  const p1 = q.load(undefined);
  const p2 = q.load("svc-internet");
  await Promise.all([p1, p2]);
  assert(seen.length === 2, "dos cargas tras cola");
  assert(seen[0] === null, "primera: reload");
  assert(seen[1] === "svc-internet", "segunda: Ver estado no se pierde");
}

// --- Agrupación UI (espejo de groupServicesByType) ---
{
  const TYPE_ORDER = ["internet", "tv", "movil", "telefonia", "other"];
  function groupServicesByType(items) {
    const buckets = new Map();
    for (const item of items) {
      const tip = TYPE_ORDER.includes(item.type) ? item.type : "other";
      const list = buckets.get(tip);
      if (list) list.push(item);
      else buckets.set(tip, [item]);
    }
    const out = [];
    for (const tip of TYPE_ORDER) {
      const list = buckets.get(tip);
      if (list?.length) out.push({ type: tip, items: list });
    }
    return out;
  }
  function servicesCountLabel(n) {
    if (n <= 0) return "0 servicios";
    if (n === 1) return "1 servicio";
    return `${n} servicios`;
  }
  // Caso 1: 1 Internet → un grupo
  {
    const g = groupServicesByType([
      { id: "i1", type: "internet", product: "Fibra 100", active: true },
    ]);
    assert(g.length === 1 && g[0].type === "internet", "caso1 grupos");
    assert(g[0].items.length === 1 && g[0].items[0].id === "i1", "caso1 instancia");
  }

  // Caso 2: 4 IMOWI distintos id → un grupo, 4 instancias
  {
    const items = [1, 2, 3, 4].map((n) => ({
      id: `m${n}`,
      type: "movil",
      product: `Imowi ${n} GB`,
      active: true,
    }));
    const g = groupServicesByType(items);
    assert(g.length === 1 && g[0].type === "movil", "caso2 grupo");
    assert(g[0].items.length === 4, "caso2 cuatro");
    assert(servicesCountLabel(4) === "4 servicios", "caso2 label");
  }

  // Caso 3: mismo product, distinto id → 2 instancias
  {
    const g = groupServicesByType([
      { id: "A", type: "movil", product: "Imowi 10 GB", active: true },
      { id: "B", type: "movil", product: "Imowi 10 GB", active: true },
    ]);
    assert(g[0].items.length === 2, "caso3 dos ids");
    assert(g[0].items.map((i) => i.id).join(",") === "A,B", "caso3 ids");
  }

  // Caso A: line_msisdn → Línea ····XXXX
  {
    const item = {
      id: "140053",
      type: "movil",
      product: "Imowi 5 GB",
      line_msisdn: "2212345643",
      active: true,
    };
    assert(maskLineMsisdn(item.line_msisdn) === "····5643", "casoA mask");
    assert(lineLabelForDisplay(item) === "Línea ····5643", "casoA label");
  }

  // Caso B: mismo plan, dos líneas → ambas visibles y diferenciadas
  {
    const items = [
      { id: "100", type: "movil", product: "Imowi 5 GB", line_msisdn: "2212345643", active: true },
      { id: "200", type: "movil", product: "Imowi 5 GB", line_msisdn: "2212345650", active: true },
    ];
    const g = groupServicesByType(items);
    assert(g[0].items.length === 2, "casoB dos instancias");
    assert(lineLabelForDisplay(items[0]) === "Línea ····5643", "casoB 5643");
    assert(lineLabelForDisplay(items[1]) === "Línea ····5650", "casoB 5650");
  }

  // Caso C: line_msisdn=null → no "Línea"; ignora msisdn/id/cuenta
  {
    const item = { id: "m1", type: "movil", product: "Imowi 5 GB", line_msisdn: null };
    assert(lineLabelForDisplay(item) === null, "casoC sin línea");
    assert(lineLabelForDisplay({ ...item, msisdn: "2231111001" }) === null, "casoC ignora msisdn");
    assert(maskLineMsisdn(null) === null, "casoC mask null");
  }

  // Caso D / Caso 5: varios tipos → agrupación intacta
  {
    const g = groupServicesByType([
      { id: "i", type: "internet", product: "Fibra", active: true },
      { id: "m1", type: "movil", product: "5GB", active: true },
      { id: "m2", type: "movil", product: "10GB", active: true },
      { id: "t", type: "tv", product: "Sensa", active: true },
    ]);
    assert(g.map((x) => x.type).join(",") === "internet,tv,movil", "casoD orden");
    assert(g.find((x) => x.type === "movil").items.length === 2, "casoD movil");
  }

  // Caso C — Internet×1, IMOWI×4, TV×2
  {
    const items = [
      { id: "i1", type: "internet", product: "Fibra 100", active: true },
      ...[1, 2, 3, 4].map((n) => ({
        id: `imowi-${n}`,
        type: "movil",
        product: n % 2 ? "Imowi 5 GB" : "Imowi 10 GB",
        active: true,
      })),
      { id: "tv1", type: "tv", product: "Sensa", active: true },
      { id: "tv2", type: "tv", product: "Sensa Plus", active: true },
    ];
    const g = groupServicesByType(items);
    assert(g.length === 3, "casoC tres grupos");
    assert(g.find((x) => x.type === "internet").items.length === 1, "casoC inet");
    assert(g.find((x) => x.type === "movil").items.length === 4, "casoC imowi");
    assert(g.find((x) => x.type === "tv").items.length === 2, "casoC tv");
    assert(items.length === 7, "casoC no pierde elementos del array");
  }

  // Caso 6: Internet conserva Ver estado + id
  {
    const item = { id: "casa-99", type: "internet", product: "Fibra", active: true };
    const actions = internetQuickActions();
    assert(actions[0].label === "Ver estado", "caso6 cta");
    assert(ctaFor(item.type) === "connectivity+wifi", "caso6 connectivity");
    assert(item.id === "casa-99", "caso6 service.id");
  }

  // Caso E — Ver todos: expandir todos los tipos sin perder instancias
  {
    const items = [
      { id: "i1", type: "internet", product: "Fibra", active: true },
      { id: "m1", type: "movil", product: "5GB", active: true },
      { id: "m2", type: "movil", product: "10GB", active: true },
      { id: "t1", type: "tv", product: "Sensa", active: true },
    ];
    const g = groupServicesByType(items);
    const expanded = {};
    for (const grp of g) expanded[grp.type] = true;
    const visibleIds = g.flatMap((grp) => (expanded[grp.type] ? grp.items.map((i) => i.id) : []));
    assert(visibleIds.length === items.length, "casoE todas visibles");
    assert(visibleIds.sort().join(",") === items.map((i) => i.id).sort().join(","), "casoE ids intactos");
    assert(g.length > 1, "casoE Ver todos aplica con varios grupos");
  }

  // other no se descarta
  {
    const g = groupServicesByType([
      { id: "o1", type: "other", product: "Capital Social", active: true },
    ]);
    assert(g.length === 1 && g[0].type === "other" && g[0].items[0].id === "o1", "other visible");
  }
}

console.log("verify-services: ok");
