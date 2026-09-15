import { Pressable, StyleSheet, View } from "react-native";

import { colors, radius, sizes, spacing } from "../theme";
import { Text } from "./Text";

export function CsatBar({
  onPick,
  busy,
}: {
  onPick: (n: number) => void;
  busy?: boolean;
}) {
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

const styles = StyleSheet.create({
  wrap: {
    marginBottom: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  title: { marginBottom: spacing.sm, textAlign: "center" },
  stars: { flexDirection: "row", justifyContent: "space-between", gap: spacing.xs },
  starBtn: {
    flex: 1,
    minHeight: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  pressed: { backgroundColor: colors.brandMuted, borderColor: colors.brand },
  star: { color: colors.text, fontSize: 16, fontWeight: "700" },
  off: { opacity: 0.5 },
});
