import { StyleSheet, View, type ViewProps } from "react-native";

import { colors, elevation, radius, spacing } from "../theme";

export function Card({ style, ...rest }: ViewProps) {
  return <View style={[styles.card, style]} {...rest} />;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    ...elevation.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
});
