import type { TextStyle } from "react-native";

import { fontSize } from "./tokens";

/** Roles tipográficos sobre la escala de design/tokens.json. El cuerpo no baja de 13 px. */
export const textRoles = {
  kicker: { fontSize: fontSize.xs, lineHeight: 16, fontWeight: "600", letterSpacing: 0.2 },
  label: { fontSize: fontSize.xs, lineHeight: 16, fontWeight: "500" },
  meta: { fontSize: fontSize.xs, lineHeight: 16, fontWeight: "400" },
  section: { fontSize: fontSize.sm, lineHeight: 20, fontWeight: "600", letterSpacing: 0.3 },
  error: { fontSize: fontSize.sm, lineHeight: 20, fontWeight: "500" },
  subtitle: { fontSize: fontSize.md, lineHeight: 20, fontWeight: "400" },
  body: { fontSize: fontSize.base, lineHeight: 22, fontWeight: "400" },
  button: { fontSize: fontSize.lg, lineHeight: 20, fontWeight: "700" },
  title: { fontSize: fontSize.title, lineHeight: 28, fontWeight: "700" },
  heading: { fontSize: fontSize.headline, lineHeight: 32, fontWeight: "700" },
  greeting: { fontSize: fontSize.display, lineHeight: 36, fontWeight: "800" },
} satisfies Record<string, TextStyle>;

export type TextRole = keyof typeof textRoles;
