# EKO 2.3G-M — MOBILE TICKET PUSH CONTRACT & ACTIVITY DEEP-LINK

**Status:** PASS (mobile contract only)  
**Depends on:** 2.3G BLOCKED (backend emission deferred)  
**Backend impact:** NONE — ticket proactive **not** enabled  

---

## 1. Purpose

Establecer el contrato de **consumo** móvil para:

```text
{ "tipo": "ticket", "ticket_id": "<id>", "event": "created|updated|resolved|closed" }
  → Activity
  → GET /portal/tickets/{id} (auth)
  → detalle existente
```

Sin emisión backend. Sin segundo mecanismo de push.

---

## 2. Existing push contract (before)

| Payload | Intent |
|---|---|
| `tipo=incidente` + `outage_id` | Home + `refreshConnectivity` |
| `mensaje_agente` / `conversacion_id` | Eko |
| else | Home |

`tab: "activity"` existía en el tipo TS pero **no** se seteaba desde push.

---

## 3. Activity navigation (reused)

- `AppShell` ya tenía `focusTicketId` → `ActivityScreen` → `openDetail(ticketId)`.
- Home → `onOpenActivity(ticketId)` tras crear reclamo.
- 2.3G-M: push `tipo=ticket` alimenta el mismo `focusTicketId` vía `pushFocusSeq`.

No stack nuevo. No segunda pantalla de ticket.

---

## 4. Ticket payload type

```ts
type TicketPushPayload = {
  tipo: "ticket";
  ticket_id: string;
  event: "created" | "updated" | "resolved" | "closed" | "";
};
```

Vocabulario alineado a candidatos 2.3G; **mobile no habilita emisión**.

`PushOpenIntent` ahora incluye `ticket_id` (siempre presente; vacío si N/A).

---

## 5. Navigation behavior

| Condition | Result |
|---|---|
| `tipo=ticket` + `ticket_id` | `tab=activity`, focus + `api.getTicket` |
| `tipo=ticket` sin / malformed id | `tab=activity`, lista (sin fabricar) |
| Tap (background / cold start) | `onOpen` / `consumeInitialPushResponse` |
| Foreground receipt | **no** navega (igual que antes; solo incidente refresca connectivity) |

---

## 6. Ticket resolution & security

- `ticket_id` = referencia de navegación, **no** autorización.
- Contenido siempre desde `GET /api/v1/portal/tickets/{id}` con JWT portal.
- Backend ya responde **404** si el ticket no pertenece al abonado.
- `openDetail` en fallo: `detail=null`, error visible, sin fabricar.
- Push **no** incluye detalle/notas/operador (contrato mobile no los lee).

---

## 7. Backward compatibility

- Incidente / Eko / Activity manual: sin cambio semántico.
- `tipo=ticket` se evalúa **antes** que `conversacion_id` para evitar misroute.

---

## 8. Files

| Path | Change |
|---|---|
| `mobile/src/pushIncidente.ts` | `parseTicketPush`, intent Activity |
| `mobile/src/push.ts` | re-exports |
| `mobile/App.tsx` | aplica `ticket_id` → push focus |
| `mobile/src/navigation/AppShell.tsx` | `pushFocusTicketId` / `pushFocusSeq` |
| `mobile/src/screens/ActivityScreen.tsx` | clear selection si openDetail falla |
| `mobile/src/hooks/useTickets.ts` | `openDetail` → `boolean`, clear detail on error |
| `mobile/scripts/verify-push-incidente.mjs` | casos ticket + regresión |
| `docs/EKO-2.3G-M-MOBILE-TICKET-PUSH-CONTRACT.md` | este doc |

---

## 9. Explicit non-goals

No backend proactive, no `ticket.*` en `SUPPORTED_PROACTIVE_EVENTS`, no claims, no Expo desde tickets, no LLM.

---

## 10. Unblock path for 2.3G-B

Backend puede emitir Expo `data` con este contrato y reutilizar policy/delivery **después** de extender claims fuera de campos outage.
