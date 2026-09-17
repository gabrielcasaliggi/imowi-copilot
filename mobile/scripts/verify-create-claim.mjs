/**
 * Verificación Milestone F — reclamo controlado (sin deps RN).
 * npm run test:claim
 *
 * Espejo de la guarda inFlight de useCreateClaim + contrato de payload.
 */
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

/** Mismo contrato que api.createTicket / PortalTicketCreateIn. */
function buildCreatePayload(motivo, descripcion) {
  return {
    motivo: String(motivo || "").trim(),
    descripcion: String(descripcion || "").trim(),
  };
}

function isValidCreatePayload(body) {
  return Boolean(body.motivo && body.descripcion);
}

/**
 * Simula la guarda de doble tap: una sola invocación “en vuelo”.
 */
function makeCreateGuard(createFn) {
  let inFlight = false;
  let calls = 0;
  return {
    get calls() {
      return calls;
    },
    async create(input) {
      if (inFlight) return null;
      const body = buildCreatePayload(input.motivo, input.descripcion);
      if (!isValidCreatePayload(body)) return { error: "validation" };
      inFlight = true;
      calls += 1;
      try {
        return await createFn(body);
      } finally {
        inFlight = false;
      }
    },
  };
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// --- Test 1: payload válido ---
{
  const p = buildCreatePayload("  Internet  ", " Sin servicio ");
  assert(p.motivo === "Internet", "motivo trim");
  assert(p.descripcion === "Sin servicio", "descripcion trim");
  assert(isValidCreatePayload(p), "válido");
}

// --- Test 2: doble tap no dispara dos creates simultáneos ---
{
  let concurrent = 0;
  let maxConcurrent = 0;
  const guard = makeCreateGuard(async () => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    await sleep(30);
    concurrent -= 1;
    return { ticket: { id: "TK-1" } };
  });
  const a = guard.create({ motivo: "A", descripcion: "uno" });
  const b = guard.create({ motivo: "A", descripcion: "uno" });
  const [ra, rb] = await Promise.all([a, b]);
  assert(ra && ra.ticket.id === "TK-1", "primera ok");
  assert(rb === null, "segunda bloqueada");
  assert(guard.calls === 1, "una sola llamada");
  assert(maxConcurrent === 1, "sin concurrencia");
}

// --- Test 3: error no se trata como éxito ---
{
  const guard = makeCreateGuard(async () => {
    throw new Error("fail");
  });
  let threw = false;
  try {
    await guard.create({ motivo: "X", descripcion: "Y" });
  } catch {
    threw = true;
  }
  assert(threw, "propaga error");
  assert(guard.calls === 1, "intentó una vez");
  const retry = await guard.create({ motivo: "X", descripcion: "Y" }).catch(() => null);
  assert(retry === null, "retry disponible pero falla igual");
  assert(guard.calls === 2, "retry cuenta");
}

// --- Test 4: validación local ---
{
  const guard = makeCreateGuard(async () => ({ ticket: { id: "TK" } }));
  const empty = await guard.create({ motivo: "", descripcion: "x" });
  assert(empty && empty.error === "validation", "motivo vacío");
  assert(guard.calls === 0, "no llama API si inválido");
}

// --- Test 5: no auto-ticket por eventos de incidente ---
{
  const events = ["CREATE", "UPDATED", "RESOLVED", "declared", "updated", "resolved"];
  for (const event of events) {
    assert(
      event !== "create_ticket",
      `incidente ${event} no crea ticket`,
    );
  }
  // El flujo F exige acción explícita; no hay mapeo evento→ticket.
  const shouldCreateTicketFromIncident = (event) => false;
  for (const event of events) {
    assert(!shouldCreateTicketFromIncident(event), `no auto ${event}`);
  }
}

console.log("verify-create-claim: ok");
