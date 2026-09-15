import { StyleSheet, View } from "react-native";

import { colors, radius, spacing } from "../theme";
import { Text } from "./Text";

export function Badge({ label }: { label: string }) {
  return (
    <View style={styles.badge}>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.brand,
    backgroundColor: colors.brandMuted,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  label: { color: colors.brand, fontSize: 12, fontWeight: "600" },
});
