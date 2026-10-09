#!/usr/bin/env node
/**
 * Genera los tokens de diseño desde design/tokens.json (fuente única de verdad).
 *
 *   node scripts/design-tokens.mjs          → escribe los archivos generados
 *   node scripts/design-tokens.mjs --check  → falla si están desactualizados (CI)
 *
 * Salidas:
 *   mobile/src/theme/tokens.ts       (app Expo)
 *   frontend/src/styles/tokens.css   (variables CSS --eko-*)
 *   mobile/app.json                  (solo los backgroundColor del splash: bg claro / oscuro)
 *
 * Sin dependencias: solo Node.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(ROOT, "design", "tokens.json");
const OUT_TS = join(ROOT, "mobile", "src", "theme", "tokens.ts");
const OUT_CSS = join(ROOT, "frontend", "src", "styles", "tokens.css");
const APP_JSON = join(ROOT, "mobile", "app.json");
const MODES = ["light", "dark"];
const HEADER = "Generado por scripts/design-tokens.mjs desde design/tokens.json. No editar a mano.";

export function loadTokens(path = SOURCE) {
  const tokens = JSON.parse(readFileSync(path, "utf8"));
  for (const [name, value] of Object.entries(tokens.color)) {
    for (const mode of MODES) {
      if (!/^#[0-9A-Fa-f]{6}$/.test(value[mode] ?? "")) {
        throw new Error(`design/tokens.json: color.${name}.${mode} debe ser un hex #RRGGBB (vale ${JSON.stringify(value[mode])})`);
      }
    }
  }
  return tokens;
}

function kebab(name) {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

function objLiteral(obj, indent = "  ") {
  const lines = Object.entries(obj).map(([k, v]) => `${indent}${/^[A-Za-z_$][\w$]*$/.test(k) ? k : JSON.stringify(k)}: ${JSON.stringify(v)},`);
  return `{\n${lines.join("\n")}\n${indent.slice(2)}}`;
}

export function renderTs(tokens) {
  const names = Object.keys(tokens.color);
  const palette = (mode) =>
    objLiteral(Object.fromEntries(names.map((n) => [n, tokens.color[n][mode]])), "    ");
  return `// ${HEADER}

export type ColorScheme = "light" | "dark";

export type ThemeColors = {
${names.map((n) => `  ${n}: string;`).join("\n")}
};

export const palette: Record<ColorScheme, ThemeColors> = {
  light: ${palette("light")},
  dark: ${palette("dark")},
};

export const fontFamily = ${JSON.stringify(tokens.font.family)};

export const fontWeight = ${objLiteral(tokens.font.weight)} as const;

export const fontSize = ${objLiteral(tokens.font.size)} as const;

export const bodyMinFontSize = ${tokens.font.bodyMin};

export const radius = ${objLiteral(tokens.radius)} as const;

export const space = ${objLiteral(tokens.space)} as const;

export const size = ${objLiteral(tokens.size)} as const;
`;
}

export function renderCss(tokens) {
  const colorVars = (mode) =>
    Object.entries(tokens.color)
      .map(([n, v]) => `  --eko-${kebab(n)}: ${v[mode]};`)
      .join("\n");
  const scale = (prefix, obj, unit = "px") =>
    Object.entries(obj)
      .map(([k, v]) => `  --eko-${prefix}-${kebab(k)}: ${v}${unit};`)
      .join("\n");
  const weights = Object.entries(tokens.font.weight)
    .map(([k, v]) => `  --eko-font-weight-${kebab(k)}: ${v};`)
    .join("\n");
  return `/* ${HEADER} */

/* Modo claro (default) */
:root,
html[data-theme="light"] {
  color-scheme: light;
${colorVars("light")}
}

/* Modo oscuro */
html[data-theme="dark"] {
  color-scheme: dark;
${colorVars("dark")}
}

/* Escalas (iguales en ambos modos) */
:root {
  --eko-font-family: "${tokens.font.family}";
${weights}
${scale("font-size", tokens.font.size)}
${scale("radius", tokens.radius)}
${scale("space", tokens.space)}
${scale("size", tokens.size)}
}
`;
}

/** Splash nativo: fondo `bg` claro por defecto y `bg` oscuro en modo oscuro (Android e iOS). */
export function renderAppJson(tokens, currentText) {
  const app = JSON.parse(currentText);
  const { light, dark } = tokens.color.bg;
  const expo = app.expo;
  expo.splash = { ...expo.splash, backgroundColor: light };
  for (const platform of ["android", "ios"]) {
    expo[platform] = expo[platform] ?? {};
    const splash = { ...expo.splash, ...expo[platform].splash, backgroundColor: light };
    splash.dark = { ...expo.splash, ...splash.dark, backgroundColor: dark };
    delete splash.dark.dark;
    expo[platform].splash = splash;
  }
  return JSON.stringify(app, null, 2) + "\n";
}

function main() {
  const check = process.argv.includes("--check");
  const tokens = loadTokens();
  const outputs = [
    [OUT_TS, renderTs(tokens)],
    [OUT_CSS, renderCss(tokens)],
    [APP_JSON, renderAppJson(tokens, readFileSync(APP_JSON, "utf8"))],
  ];
  const stale = [];
  for (const [path, content] of outputs) {
    const current = existsSync(path) ? readFileSync(path, "utf8") : null;
    if (current === content) continue;
    if (check) {
      stale.push(relative(ROOT, path));
    } else {
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, content);
      console.log(`escrito ${relative(ROOT, path)}`);
    }
  }
  if (stale.length) {
    console.error(
      `Tokens desactualizados respecto de design/tokens.json: ${stale.join(", ")}.\n` +
        "Correr `node scripts/design-tokens.mjs` y commitear los archivos generados.",
    );
    process.exit(1);
  }
  if (check) console.log("tokens generados al día");
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
