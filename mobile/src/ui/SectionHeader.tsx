import { StyleSheet } from "react-native";

import { spacing } from "../theme";
import { Text } from "./Text";

export function SectionHeader({ title }: { title: string }) {
  return (
    <Text variant="section" style={styles.head}>
      {title}
    </Text>
  );
}

const styles = StyleSheet.create({
  head: { marginBottom: spacing.md, textTransform: "uppercase" },
});
