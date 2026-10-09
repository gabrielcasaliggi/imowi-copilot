import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  View,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { textRoles } from "../theme/typography";
import { Text } from "./Text";

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
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const off = Boolean(disabled) || loading;
  // Primario deshabilitado: fondo gris + texto onDisabled (≥ 3:1). Ghost/danger siguen con opacidad.
  const primaryOff = off && variant === "primary";
  const labelStyle = [
    styles.label,
    variant === "ghost" && styles.labelGhost,
    variant === "danger" && styles.labelDanger,
    primaryOff && styles.labelDisabled,
  ];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off }}
      disabled={off}
      style={[styles.base, styles[variant], primaryOff ? styles.primaryDisabled : off && styles.off, style]}
      {...rest}
    >
      {loading ? (
        <View style={styles.row}>
          <ActivityIndicator
            color={
              variant === "danger"
                ? colors.danger
                : variant === "ghost"
                  ? colors.primary
                  : primaryOff
                    ? colors.onDisabled
                    : colors.onPrimary
            }
          />
          <Text style={labelStyle}>{label}</Text>
        </View>
      ) : (
        <Text style={labelStyle}>{label}</Text>
      )}
    </Pressable>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    base: {
      borderRadius: t.radius.control,
      minHeight: t.size.hit,
      paddingVertical: t.space.md,
      paddingHorizontal: t.space.lg,
      alignItems: "center",
      justifyContent: "center",
    },
    primary: { backgroundColor: t.colors.primary },
    ghost: { backgroundColor: t.colors.surface, borderWidth: 1, borderColor: t.colors.border },
    danger: { backgroundColor: "transparent", borderWidth: 1, borderColor: t.colors.danger },
    off: { opacity: 0.5 },
    primaryDisabled: { backgroundColor: t.colors.disabled },
    labelDisabled: { color: t.colors.onDisabled },
    label: { ...textRoles.button, color: t.colors.onPrimary },
    labelGhost: { color: t.colors.ink, fontWeight: "600", fontSize: t.fontSize.base },
    labelDanger: { color: t.colors.danger, fontWeight: "600", fontSize: t.fontSize.md },
    row: { flexDirection: "row", alignItems: "center", gap: t.space.sm },
  });
}
