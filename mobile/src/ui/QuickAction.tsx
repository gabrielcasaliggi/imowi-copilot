import { Pressable, StyleSheet } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
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
  const styles = useThemedStyles(makeStyles);
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

function makeStyles(t: Theme) {
  const { colors, space, radius, size, fontSize } = t;
  return StyleSheet.create({
    action: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.control,
      paddingVertical: space.md,
      paddingHorizontal: space.lg,
      minHeight: size.hit,
      minWidth: "47%",
      flexGrow: 1,
      justifyContent: "center",
    },
    label: { color: colors.ink, fontWeight: "600", fontSize: fontSize.base },
  });
}
