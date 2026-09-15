import {
  StyleSheet,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";

import { colors, radius, sizes, spacing } from "../theme";
import { Text } from "./Text";

export function TextField({
  label,
  style,
  ...rest
}: TextInputProps & { label?: string }) {
  return (
    <View style={styles.wrap}>
      {label ? <Text variant="label" style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.muted}
        style={[styles.input, style]}
        {...rest}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.md },
  label: { marginBottom: spacing.xs + 2 },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    color: colors.text,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: 16,
    minHeight: sizes.hit,
  },
});
