import { Pressable, StyleSheet } from "react-native";

import { colors, radius, sizes, spacing } from "../theme";
import { Text } from "./Text";

export function QuickAction({
  label,
  onPress,
  accessibilityHint,
}: {
  label: string;
  onPress: () => void;
  accessibilityHint?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      style={styles.action}
    >
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  action: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: sizes.hit,
    minWidth: "47%",
    flexGrow: 1,
    justifyContent: "center",
  },
  label: { color: colors.text, fontWeight: "600", fontSize: 15 },
});
