import { Pressable, StyleSheet, View } from "react-native";

import { colors, radius, spacing } from "../theme";
import { Text } from "./Text";

type Tone = "warning" | "ok";

export function Banner({
  children,
  tone = "warning",
  onPress,
  actionLabel,
}: {
  children: string;
  tone?: Tone;
  onPress?: () => void;
  actionLabel?: string;
}) {
  const body = (
    <View style={[styles.base, tone === "ok" ? styles.ok : styles.warning]}>
      <Text style={[styles.copy, tone === "ok" ? styles.copyOk : styles.copyWarn]}>
        {children}
      </Text>
      {actionLabel ? (
        <Text style={[styles.action, tone === "ok" ? styles.copyOk : styles.copyWarn]}>
          {actionLabel}
        </Text>
      ) : null}
    </View>
  );
  if (onPress) {
    return (
      <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={actionLabel || children}>
        {body}
      </Pressable>
    );
  }
  return body;
}

const styles = StyleSheet.create({
  base: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  warning: {
    backgroundColor: colors.amberMuted,
    borderColor: colors.amberBorder,
  },
  ok: {
    backgroundColor: colors.brandMuted,
    borderColor: colors.brandBorder,
  },
  copy: { fontSize: 13, lineHeight: 18 },
  copyWarn: { color: colors.amber },
  copyOk: { color: colors.brand },
  action: { marginTop: spacing.sm, fontWeight: "700", fontSize: 13 },
});
