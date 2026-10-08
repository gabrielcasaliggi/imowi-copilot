import { Pressable, StyleSheet, View } from "react-native";

import { useThemedStyles, useThemePreference, type Theme, type ThemePreference } from "../theme/ThemeProvider";
import { Text } from "./Text";

const OPTIONS: { value: ThemePreference; label: string; hint: string }[] = [
  { value: "system", label: "Sistema", hint: "Usa el modo del teléfono" },
  { value: "light", label: "Claro", hint: "Fondo claro siempre" },
  { value: "dark", label: "Oscuro", hint: "Fondo oscuro siempre" },
];

/** Selector de apariencia (Cuenta). Se monta recién cuando THEME_SELECTOR_ENABLED es true. */
export function ThemeSelector() {
  const { preference, setPreference } = useThemePreference();
  const styles = useThemedStyles(makeStyles);

  return (
    <View accessibilityRole="radiogroup" accessibilityLabel="Apariencia" style={styles.group}>
      {OPTIONS.map((opt) => {
        const selected = preference === opt.value;
        return (
          <Pressable
            key={opt.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityHint={opt.hint}
            onPress={() => setPreference(opt.value)}
            style={[styles.option, selected && styles.optionSelected]}
          >
            <View style={[styles.radio, selected && styles.radioSelected]}>
              {selected ? <View style={styles.radioDot} /> : null}
            </View>
            <Text style={styles.label}>{opt.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    group: { gap: t.space.sm },
    option: {
      minHeight: t.size.hit,
      flexDirection: "row",
      alignItems: "center",
      gap: t.space.md,
      paddingHorizontal: t.space.lg,
      paddingVertical: t.space.sm,
      borderRadius: t.radius.control,
      borderWidth: 1,
      borderColor: t.colors.border,
      backgroundColor: t.colors.surface,
    },
    optionSelected: { borderColor: t.colors.primary },
    radio: {
      width: 20,
      height: 20,
      borderRadius: t.radius.pill,
      borderWidth: 2,
      borderColor: t.colors.borderStrong,
      alignItems: "center",
      justifyContent: "center",
    },
    radioSelected: { borderColor: t.colors.primary },
    radioDot: { width: 8, height: 8, borderRadius: t.radius.pill, backgroundColor: t.colors.primary },
    label: { fontSize: t.fontSize.base, fontWeight: "600", color: t.colors.ink },
  });
}
