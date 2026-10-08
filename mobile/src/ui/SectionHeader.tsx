import { StyleSheet } from "react-native";

import { space } from "../theme/tokens";
import { Text } from "./Text";

export function SectionHeader({ title }: { title: string }) {
  return (
    <Text variant="section" style={styles.head}>
      {title}
    </Text>
  );
}

const styles = StyleSheet.create({
  head: { marginBottom: space.md, textTransform: "uppercase" },
});
