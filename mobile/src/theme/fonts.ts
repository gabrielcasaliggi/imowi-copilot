import { isLoaded } from "expo-font";
import { StyleSheet, type StyleProp, type TextStyle } from "react-native";

import { fontWeight } from "./tokens";

/**
 * Manrope estático, un archivo por peso (design/tokens.json → font.weight).
 * Las claves son el nombre de familia: Android no sintetiza pesos de una fuente propia,
 * así que cada peso se pide por su familia y nunca por `fontWeight`.
 * Los nombres coinciden con los archivos para que valgan igual con `useFonts`
 * y con la fuente embebida por el plugin `expo-font` en la build nativa.
 */
export const fontFiles = {
  Manrope_400Regular: require("../../assets/fonts/Manrope_400Regular.ttf"),
  Manrope_500Medium: require("../../assets/fonts/Manrope_500Medium.ttf"),
  Manrope_600SemiBold: require("../../assets/fonts/Manrope_600SemiBold.ttf"),
  Manrope_700Bold: require("../../assets/fonts/Manrope_700Bold.ttf"),
  Manrope_800ExtraBold: require("../../assets/fonts/Manrope_800ExtraBold.ttf"),
};

type FontName = keyof typeof fontFiles;

const familyByWeight: Record<number, FontName> = {
  [fontWeight.regular]: "Manrope_400Regular",
  [fontWeight.medium]: "Manrope_500Medium",
  [fontWeight.semibold]: "Manrope_600SemiBold",
  [fontWeight.bold]: "Manrope_700Bold",
  [fontWeight.extrabold]: "Manrope_800ExtraBold",
};

/** Peso CSS/RN → familia Manrope. Pesos fuera de 400–800 se acotan al más cercano. */
export function fontFamilyForWeight(weight: TextStyle["fontWeight"]): FontName {
  let w: number;
  if (weight === "bold") w = 700;
  else if (weight === undefined || weight === "normal") w = 400;
  else w = Number(weight);
  if (!Number.isFinite(w)) w = 400;
  w = Math.min(800, Math.max(400, Math.round(w / 100) * 100));
  return familyByWeight[w];
}

/**
 * Reemplaza `fontWeight` por la familia Manrope del peso pedido.
 * Respeta un `fontFamily` explícito (p. ej. monoespaciada).
 * Si esa familia todavía no está cargada (falla o demora), deja el estilo intacto:
 * fuente del sistema con su `fontWeight`, en vez de una familia inexistente sin negritas.
 */
export function withManrope(style: StyleProp<TextStyle>): TextStyle {
  const flat = StyleSheet.flatten(style) ?? {};
  if (flat.fontFamily) return flat;
  const { fontWeight: weight, ...rest } = flat;
  const family = fontFamilyForWeight(weight);
  if (!isLoaded(family)) return flat;
  return { ...rest, fontFamily: family };
}
