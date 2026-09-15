import { StyleSheet, View } from "react-native";

import { spacing } from "../theme";
import { Text } from "./Text";

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <View style={styles.wrap}>
      <Text variant="title" style={styles.title}>{title}</Text>
      <Text variant="subtitle">{description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: spacing.xxl, paddingHorizontal: spacing.sm },
  title: { marginBottom: spacing.sm },
});
