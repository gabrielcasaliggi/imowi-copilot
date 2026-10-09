import { StyleSheet, View } from "react-native";

import { present } from "../present";
import { space } from "../theme/tokens";
import { Text } from "./Text";

export function StatusRow({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  const v = present(value);
  if (!v) return null;
  return (
    <View style={styles.row}>
      <Text variant="label">{label}</Text>
      <Text style={styles.value} numberOfLines={3}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { gap: space.xs, marginBottom: space.md },
  value: { flexShrink: 1 },
});
