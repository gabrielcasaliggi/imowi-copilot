/**
 * H-APP-1 9d — "Pagar" primario solo con saldo pendiente (src/balanceView.ts real,
 * transpilado en memoria con el typescript del paquete).
 * npm run test:balance
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ts = require("typescript");

const source = readFileSync(new URL("../src/balanceView.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { payButtonVariant } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const cases = [
  [15230.5, "primary", "saldo pendiente"],
  [0.01, "primary", "saldo pendiente mínimo"],
  [0, "ghost", "cuenta al día"],
  [-0, "ghost", "cuenta al día (-0)"],
  [-1200, "ghost", "saldo a favor"],
  [null, "ghost", "monto ilegible: no se empuja el pago"],
];

for (const [amount, expected, label] of cases) {
  assert.equal(
    payButtonVariant(amount),
    expected,
    `${label}: payButtonVariant(${amount}) debería ser "${expected}"`,
  );
}
console.log(`verify-balance: ${cases.length} casos de payButtonVariant OK`);
