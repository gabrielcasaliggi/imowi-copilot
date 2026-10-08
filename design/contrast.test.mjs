/**
 * Contraste WCAG 2.x AA de los pares declarados en design/tokens.json, en claro y oscuro.
 * Texto normal 4.5:1; texto grande y gráficos (bordes de input, anillos, íconos) 3:1.
 *
 *   node --test design/contrast.test.mjs
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { loadTokens } from "../scripts/design-tokens.mjs";

const tokens = loadTokens();
const MODES = ["light", "dark"];

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test("la fórmula coincide con valores de referencia WCAG", () => {
  assert.equal(contrastRatio("#000000", "#FFFFFF").toFixed(2), "21.00");
  assert.equal(contrastRatio("#FFFFFF", "#FFFFFF").toFixed(2), "1.00");
  assert.equal(contrastRatio("#767676", "#FFFFFF").toFixed(2), "4.54");
});

test("cada par declarado usa colores y umbrales existentes", () => {
  const { pairs, threshold } = tokens.contrast;
  assert.ok(pairs.length > 0, "contrast.pairs está vacío");
  for (const p of pairs) {
    assert.ok(tokens.color[p.fg], `par ${p.fg}/${p.bg}: color "${p.fg}" no existe en color`);
    assert.ok(tokens.color[p.bg], `par ${p.fg}/${p.bg}: color "${p.bg}" no existe en color`);
    assert.ok(threshold[p.use], `par ${p.fg}/${p.bg}: uso "${p.use}" sin umbral en contrast.threshold`);
  }
});

for (const mode of MODES) {
  test(`contraste AA en modo ${mode}`, () => {
    const failures = [];
    for (const { fg, bg, use } of tokens.contrast.pairs) {
      const min = tokens.contrast.threshold[use];
      const ratio = contrastRatio(tokens.color[fg][mode], tokens.color[bg][mode]);
      if (ratio < min) {
        failures.push(
          `  ${fg} ${tokens.color[fg][mode]} sobre ${bg} ${tokens.color[bg][mode]} (${use}): ${ratio.toFixed(2)}:1, se esperaba ≥ ${min}:1`,
        );
      }
    }
    assert.equal(failures.length, 0, `Pares que no cumplen WCAG AA en modo ${mode}:\n${failures.join("\n")}`);
  });
}

test("escalas: espaciado múltiplo de 4, cuerpo ≥ 13 px, tocables ≥ 44 px", () => {
  for (const [k, v] of Object.entries(tokens.space)) {
    assert.equal(v % 4, 0, `space.${k} = ${v} no es múltiplo de 4`);
  }
  assert.ok(tokens.font.bodyMin >= 13, `font.bodyMin = ${tokens.font.bodyMin}, se esperaba ≥ 13`);
  assert.ok(tokens.size.hit >= 44, `size.hit = ${tokens.size.hit}, se esperaba ≥ 44`);
});
