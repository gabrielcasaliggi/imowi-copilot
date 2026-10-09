/** Mi cuenta (Home): reglas de presentación del saldo. Sin RN; la prueba scripts/verify-balance.mjs. */

export type ActionVariant = "primary" | "ghost";

/**
 * "Pagar" es la acción principal solo con saldo pendiente (> 0). Con la cuenta al día,
 * saldo a favor o un monto que no se pudo leer, queda secundario: no empujar un pago
 * que no hace falta o que no podemos confirmar.
 */
export function payButtonVariant(amount: number | null): ActionVariant {
  return amount !== null && amount > 0 ? "primary" : "ghost";
}
