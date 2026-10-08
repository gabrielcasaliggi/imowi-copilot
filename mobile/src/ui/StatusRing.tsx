import { StyleSheet, View } from "react-native";

import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";

export type StatusRingTone = "ok" | "warning" | "outage" | "neutral";

const RING = 48;
const STROKE = 4;
const DOT = 12;

/**
 * Anillo de estado de conexión. Decorativo: el estado siempre se dice en texto al lado
 * (el color nunca es el único indicador). Sin SVG: borde circular sobre `track`.
 */
export function StatusRing({ tone }: { tone: StatusRingTone }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const stroke =
    tone === "ok"
      ? colors.ring
      : tone === "warning"
        ? colors.warn
        : tone === "outage"
          ? colors.danger
          : colors.track;
  const dot = tone === "neutral" ? colors.borderStrong : stroke;
  return (
    <View
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      style={[styles.ring, { borderColor: stroke }]}
    >
      <View style={[styles.dot, { backgroundColor: dot }]} />
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    ring: {
      width: RING,
      height: RING,
      borderRadius: t.radius.pill,
      borderWidth: STROKE,
      backgroundColor: t.colors.surface,
      alignItems: "center",
      justifyContent: "center",
    },
    dot: { width: DOT, height: DOT, borderRadius: t.radius.pill },
  });
}
