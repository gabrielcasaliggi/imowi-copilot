// Generado por scripts/design-tokens.mjs desde design/tokens.json. No editar a mano.

export type ColorScheme = "light" | "dark";

export type ThemeColors = {
  bg: string;
  surface: string;
  nav: string;
  border: string;
  borderStrong: string;
  ink: string;
  muted: string;
  primary: string;
  onPrimary: string;
  ok: string;
  okSoft: string;
  warn: string;
  warnSoft: string;
  danger: string;
  dangerSoft: string;
  ring: string;
  track: string;
};

export const palette: Record<ColorScheme, ThemeColors> = {
  light: {
    bg: "#F3F7F8",
    surface: "#FFFFFF",
    nav: "#FFFFFF",
    border: "#DCE6E9",
    borderStrong: "#748890",
    ink: "#0E1F26",
    muted: "#566A72",
    primary: "#0E6B78",
    onPrimary: "#FFFFFF",
    ok: "#1F7A4D",
    okSoft: "#E3F4EA",
    warn: "#8A4B00",
    warnSoft: "#FFF0D6",
    danger: "#B42318",
    dangerSoft: "#FDECEA",
    ring: "#0E8A93",
    track: "#DCE6E9",
  },
  dark: {
    bg: "#0A1120",
    surface: "#121B2D",
    nav: "#0D1627",
    border: "#22304A",
    borderStrong: "#62728C",
    ink: "#E8EEF7",
    muted: "#93A3BC",
    primary: "#3DD6C3",
    onPrimary: "#04201C",
    ok: "#4ADE9A",
    okSoft: "#12301F",
    warn: "#F2B84B",
    warnSoft: "#2B2412",
    danger: "#F87171",
    dangerSoft: "#2D1518",
    ring: "#3DD6C3",
    track: "#22304A",
  },
};

export const fontFamily = "Manrope";

export const fontWeight = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  extrabold: 800,
} as const;

export const fontSize = {
  xs: 12,
  sm: 13,
  md: 14,
  base: 15,
  lg: 16,
  xl: 17,
  title: 22,
  headline: 26,
  display: 30,
  hero: 36,
} as const;

export const bodyMinFontSize = 13;

export const radius = {
  control: 14,
  card: 18,
  cardLg: 24,
  pill: 999,
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 40,
} as const;

export const size = {
  hit: 44,
  maxContent: 480,
} as const;
