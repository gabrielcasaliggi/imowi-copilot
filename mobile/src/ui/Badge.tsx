import { StyleSheet, View } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { Text } from "./Text";

export function Badge({ label }: { label: string }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.badge}>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, radius, fontSize } = t;
  return StyleSheet.create({
    badge: {
      alignSelf: "flex-start",
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.primary,
      backgroundColor: colors.surface,
      paddingHorizontal: space.md,
      paddingVertical: space.xs,
    },
    label: { color: colors.primary, fontSize: fontSize.xs, fontWeight: "600" },
  });
}
