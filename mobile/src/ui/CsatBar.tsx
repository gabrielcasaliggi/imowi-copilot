import { Pressable, StyleSheet, View } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { Text } from "./Text";

export function CsatBar({
  onPick,
  busy,
}: {
  onPick: (n: number) => void;
  busy?: boolean;
}) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.wrap}>
      <Text variant="label" style={styles.title}>¿Cómo calificás la atención?</Text>
      <View style={styles.stars}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Pressable
            key={n}
            onPress={() => {
              if (!busy) onPick(n);
            }}
            disabled={busy}
            style={({ pressed }) => [
              styles.starBtn,
              pressed && !busy && styles.pressed,
              busy && styles.off,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Calificar ${n} de 5`}
            accessibilityState={{ disabled: Boolean(busy) }}
          >
            <Text style={styles.star}>{n}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, radius, size, fontSize } = t;
  return StyleSheet.create({
    wrap: {
      marginBottom: space.sm,
      padding: space.md,
      borderRadius: radius.control,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    title: { marginBottom: space.sm, textAlign: "center" },
    stars: { flexDirection: "row", justifyContent: "space-between", gap: space.xs },
    starBtn: {
      flex: 1,
      minHeight: size.hit,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: radius.control,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    pressed: { backgroundColor: colors.surface, borderColor: colors.primary, borderWidth: 2 },
    star: { color: colors.ink, fontSize: fontSize.lg, fontWeight: "700" },
    off: { opacity: 0.5 },
  });
}
