/**
 * Lógica pura del tema (sin React ni módulos nativos): la usa ThemeProvider y la prueba
 * scripts/verify-theme-scheme.mjs con Node.
 */
import type { ColorScheme } from "./tokens";

/** Lo que elige el abonado y se guarda en el dispositivo. Nunca se guarda el esquema resuelto. */
export type ThemePreference = "system" | "light" | "dark";

export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

/**
 * Si el sistema no informa modo (`useColorScheme()` → null/undefined), "Sistema" se resuelve
 * a claro: es el modo por defecto de Android (`values/`, tema DayNight) y del splash claro de
 * app.json, así que la app coincide con lo que el teléfono muestra sin preferencia.
 */
export const SYSTEM_SCHEME_FALLBACK: ColorScheme = "light";

/** Valor guardado → elección válida, o null si falta o es inválido (p. ej. un esquema viejo). */
export function parsePreference(raw: string | null | undefined): ThemePreference | null {
  return raw && (THEME_PREFERENCES as readonly string[]).includes(raw) ? (raw as ThemePreference) : null;
}

/**
 * Esquema a pintar. Con "system" usa el valor de `useColorScheme()`; "light"/"dark" lo ignoran.
 * Con el selector apagado la app queda fija en oscuro.
 */
export function resolveScheme(
  preference: ThemePreference,
  system: string | null | undefined,
  selectorEnabled: boolean,
): ColorScheme {
  if (!selectorEnabled) return "dark";
  if (preference !== "system") return preference;
  if (system === "light" || system === "dark") return system;
  return SYSTEM_SCHEME_FALLBACK;
}
