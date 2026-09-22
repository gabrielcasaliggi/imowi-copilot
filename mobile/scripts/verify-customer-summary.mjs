/**
 * Verificación Fase 2E — contrato Customer Summary (sin deps RN).
 * npm run test:customer-summary
 */
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const DOMAIN_STATUS = new Set([
  "ok",
  "empty",
  "stale",
  "unavailable",
  "not_available",
  "omitted",
  "partial",
]);

const OV_IDS = new Set(["pay", "invoice", "payment_slip"]);

function assertDomain(name, domain) {
  assert(domain && typeof domain === "object", `${name}: domain object`);
  assert(DOMAIN_STATUS.has(domain.status), `${name}: status inválido ${domain.status}`);
  assert(
    domain.reason_code === null || typeof domain.reason_code === "string",
    `${name}: reason_code`,
  );
}

/** Espejo de uso Home: no inventar $0 ante unavailable sin amount. */
function balanceMontoForUi(billing) {
  const amount = billing?.data?.balance?.amount;
  if (billing?.status === "unavailable" && (amount === undefined || amount === null || amount === "")) {
    return null;
  }
  return typeof amount === "string" ? amount : null;
}

function parseCustomerSummary(body) {
  assert(body && typeof body === "object", "body");
  for (const k of ["customer", "account", "services", "billing", "connectivity", "tickets"]) {
    assertDomain(k, body[k]);
  }
  assert(body.meta && typeof body.meta.generated_at === "string", "meta.generated_at");
  assert(Array.isArray(body.meta.include), "meta.include");
  assert(Array.isArray(body.meta.refresh_applied), "meta.refresh_applied");

  // Customer: sin DNI/email/teléfono
  if (body.customer.status === "ok" && body.customer.data) {
    const c = body.customer.data;
    assert(typeof c.id === "string" && c.id, "customer.id");
    assert(!("dni" in c), "customer no debe exponer dni");
    assert(!("email" in c), "customer no debe exponer email");
    assert(!("telefono" in c) && !("telefono_e164" in c), "customer no debe exponer teléfono");
  }

  // Account: data.status ≠ domain.status
  if (body.account.data) {
    assert("status" in body.account.data, "account.data.status comercial");
    assert("client_number" in body.account.data, "account.data.client_number");
  }

  // Services items sin login
  if (body.services.data?.items) {
    assert(Array.isArray(body.services.data.items), "services.items");
    for (const it of body.services.data.items) {
      assert(it.id, "service.id");
      assert(!("login" in it), "service no debe exponer login");
    }
  }

  // Billing balance
  if (body.billing.data?.balance) {
    const b = body.billing.data.balance;
    assert(typeof b.amount === "string", "balance.amount string");
    assert(b.currency === "ARS", "balance.currency ARS");
    assert(b.as_of === null || typeof b.as_of === "string", "balance.as_of");
  }

  // OV links solo ids conocidos; urls del backend
  if (body.billing.data?.ov?.links) {
    for (const link of body.billing.data.ov.links) {
      assert(OV_IDS.has(link.id), `ov id desconocido: ${link.id}`);
      assert(link.id !== "payment_notice", "no payment_notice");
      if (link.available && link.url) {
        assert(String(link.url).startsWith("http"), "ov url http");
      }
    }
  }

  // Connectivity omit
  if (body.connectivity.status === "omitted") {
    assert(body.connectivity.data === null, "connectivity omitted → data null");
  }

  // Tickets sin eventos
  if (body.tickets.data?.items) {
    for (const t of body.tickets.data.items) {
      assert(!("eventos" in t), "ticket summary sin eventos");
    }
  }

  return body;
}

function buildQuery(opts = {}) {
  const params = new URLSearchParams();
  if (opts.include) params.set("include", opts.include);
  if (opts.refresh) params.set("refresh", opts.refresh);
  if (opts.connectivity) params.set("connectivity", opts.connectivity);
  if (opts.service_id) params.set("service_id", opts.service_id);
  // Nunca identidad en query
  assert(!opts.abonado_id, "no abonado_id en query");
  assert(!opts.dni, "no dni en query");
  const qs = params.toString();
  return qs ? `/api/v1/portal/customer-summary?${qs}` : "/api/v1/portal/customer-summary";
}

// --- Fixtures ---

const FIXTURE_HOME = {
  customer: {
    status: "ok",
    data: { id: "abo-1", display_name: "María González", organization_id: "org-1" },
    reason_code: null,
  },
  account: {
    status: "stale",
    data: { client_number: "200", status: "activo", plan: "Fibra 100" },
    reason_code: "stale_snapshot",
  },
  services: {
    status: "ok",
    data: {
      checked_at: "t",
      items: [
        { id: "i1", type: "internet", label: "Fibra", product: null, active: true },
        { id: "i2", type: "internet", label: "BAI", product: null, active: true },
      ],
    },
    reason_code: null,
  },
  billing: {
    status: "stale",
    data: {
      balance: { amount: "1500.00", currency: "ARS", as_of: null, freshness: "snapshot" },
      ov: {
        status: "partial",
        checked_at: "t",
        actions: { can_open_chat: true },
        links: [
          { id: "pay", label: "Pagar", url: "https://ov.example/#/pay", available: true, mode: "public" },
          { id: "invoice", label: "Ver factura", url: "https://ov.example/#/my", available: true, mode: "public" },
          { id: "payment_slip", label: "Talón", url: null, available: false, mode: "public" },
        ],
        reason_code: "insufficient_data",
        mode: "public",
        authenticated: false,
      },
    },
    reason_code: "stale_snapshot",
  },
  connectivity: { status: "omitted", data: null, reason_code: null },
  tickets: { status: "empty", data: { items: [] }, reason_code: null },
  meta: {
    generated_at: "2026-01-01T00:00:00+00:00",
    include: ["customer", "account", "services", "billing", "tickets", "ov"],
    refresh_applied: [],
  },
};

const FIXTURE_BILLING_ZERO = {
  ...FIXTURE_HOME,
  billing: {
    status: "ok",
    data: {
      balance: { amount: "0", currency: "ARS", as_of: "t", freshness: "snapshot" },
    },
    reason_code: null,
  },
};

const FIXTURE_BILLING_UNAVAILABLE_NO_AMOUNT = {
  ...FIXTURE_HOME,
  billing: {
    status: "unavailable",
    data: {},
    reason_code: "source_unavailable",
  },
};

const FIXTURE_BILLING_UNAVAILABLE_WITH_SNAPSHOT = {
  ...FIXTURE_HOME,
  billing: {
    status: "unavailable",
    data: {
      balance: { amount: "99.00", currency: "ARS", as_of: null, freshness: "snapshot" },
    },
    reason_code: "source_unavailable",
  },
};

// --- Tests ---

parseCustomerSummary(FIXTURE_HOME);
assert(buildQuery({ connectivity: "omit" }).includes("connectivity=omit"), "query omit");
assert(buildQuery({}).endsWith("/customer-summary"), "default path");
assert(
  balanceMontoForUi(FIXTURE_HOME.billing) === "1500.00",
  "deuda > 0",
);
assert(balanceMontoForUi(FIXTURE_BILLING_ZERO.billing) === "0", "deuda = 0 string");
assert(
  balanceMontoForUi(FIXTURE_BILLING_UNAVAILABLE_NO_AMOUNT.billing) === null,
  "unavailable sin amount → no inventar 0",
);
assert(
  balanceMontoForUi(FIXTURE_BILLING_UNAVAILABLE_WITH_SNAPSHOT.billing) === "99.00",
  "unavailable con snapshot preserva amount",
);

// domain.status ≠ account.data.status
assert(FIXTURE_HOME.account.status === "stale", "domain stale");
assert(FIXTURE_HOME.account.data.status === "activo", "comercial activo");

// multi-internet
assert(FIXTURE_HOME.services.data.items.length === 2, "multi internet");
assert(
  FIXTURE_HOME.services.data.items.every((i) => i.type === "internet"),
  "ambos internet",
);

// connectivity omitted = no probe semantics
assert(FIXTURE_HOME.connectivity.status === "omitted", "home omit");
assert(FIXTURE_HOME.connectivity.data === null, "home no probe payload");

// suspended service
const suspended = {
  ...FIXTURE_HOME,
  services: {
    status: "ok",
    data: {
      checked_at: "t",
      items: [
        {
          id: "s1",
          type: "internet",
          label: "Fibra",
          product: null,
          active: false,
        },
      ],
    },
    reason_code: null,
  },
};
parseCustomerSummary(suspended);
assert(suspended.services.data.items[0].active === false, "suspended active=false");

console.log("verify-customer-summary: OK");
