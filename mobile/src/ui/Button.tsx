import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { colors, radius, sizes, spacing, typography } from "../theme";

type Variant = "primary" | "ghost" | "danger";

export function Button({
  label,
  loading,
  variant = "primary",
  disabled,
  style,
  ...rest
}: Omit<PressableProps, "style"> & {
  label: string;
  loading?: boolean;
  variant?: Variant;
  style?: StyleProp<ViewStyle>;
}) {
  const off = Boolean(disabled) || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off }}
      disabled={off}
      style={[styles.base, styles[variant], off && styles.off, style]}
      {...rest}
    >
      {loading ? (
        <View style={styles.row}>
          <ActivityIndicator
            color={
              variant === "danger"
                ? colors.danger
                : variant === "ghost"
                  ? colors.brand
                  : colors.onBrand
            }
          />
          <Text style={[styles.label, variant === "ghost" && styles.labelGhost, variant === "danger" && styles.labelDanger]}>
            {label}
          </Text>
        </View>
      ) : (
        <Text style={[styles.label, variant === "ghost" && styles.labelGhost, variant === "danger" && styles.labelDanger]}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.md,
    minHeight: sizes.hit,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  primary: { backgroundColor: colors.brand },
  ghost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  danger: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.danger },
  off: { opacity: 0.5 },
  label: { ...typography.button, color: colors.onBrand },
  labelGhost: { color: colors.text, fontWeight: "600", fontSize: 15 },
  labelDanger: { color: colors.danger, fontWeight: "600", fontSize: 14 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
});
