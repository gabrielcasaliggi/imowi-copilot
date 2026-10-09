/**
 * H-APP-1 9c-2 — lógica pura del tema: src/theme/scheme.ts, el mismo archivo que usa la app.
 * Se transpila en memoria con `typescript` (devDependency) para no depender de que Node
 * traiga soporte de TypeScript.
 * npm run test:theme
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ts = require("typescript");

const source = readFileSync(new URL("../src/theme/scheme.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { SYSTEM_SCHEME_FALLBACK, parsePreference, resolveScheme } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const cases = [
  // [elección, useColorScheme(), selector, esperado, descripción]
  ["system", "dark", true, "dark", "Sistema sigue al teléfono en oscuro"],
  ["system", "light", true, "light", "Sistema sigue al teléfono en claro"],
  ["system", null, true, SYSTEM_SCHEME_FALLBACK, "Sistema sin dato (null) cae al fallback documentado"],
  ["system", undefined, true, SYSTEM_SCHEME_FALLBACK, "Sistema sin dato (undefined) cae al fallback"],
  ["system", "unspecified", true, SYSTEM_SCHEME_FALLBACK, "Sistema con valor desconocido cae al fallback"],
  ["light", "dark", true, "light", "Claro ignora al teléfono en oscuro"],
  ["light", null, true, "light", "Claro ignora al teléfono sin dato"],
  ["dark", "light", true, "dark", "Oscuro ignora al teléfono en claro"],
  ["dark", null, true, "dark", "Oscuro ignora al teléfono sin dato"],
  ["system", "light", false, "dark", "Selector apagado: fijo en oscuro"],
  ["light", "light", false, "dark", "Selector apagado ignora la elección"],
];

let failures = 0;
for (const [pref, system, enabled, expected, label] of cases) {
  const got = resolveScheme(pref, system, enabled);
  if (got !== expected) {
    failures += 1;
    console.error(
      `FAIL ${label}: resolveScheme(${JSON.stringify(pref)}, ${JSON.stringify(system)}, ${enabled}) = ${got}, se esperaba ${expected}`,
    );
  }
}

assert.equal(SYSTEM_SCHEME_FALLBACK, "light", "el fallback documentado de 'Sistema' sin dato es claro");

// Lo guardado es la elección; un esquema resuelto u otro valor no es una preferencia válida.
assert.equal(parsePreference("system"), "system");
assert.equal(parsePreference("light"), "light");
assert.equal(parsePreference("dark"), "dark");
assert.equal(parsePreference(null), null);
assert.equal(parsePreference(""), null);
assert.equal(parsePreference("automatic"), null);
assert.equal(parsePreference("DARK"), null);

if (failures) {
  console.error(`${failures} caso(s) de resolveScheme fallaron`);
  process.exit(1);
}
console.log(`verify-theme-scheme: ${cases.length} casos de resolveScheme + parsePreference OK`);
