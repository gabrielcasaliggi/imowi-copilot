import { StyleSheet, View, type ViewProps } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";

export function Card({ style, ...rest }: ViewProps) {
  const styles = useThemedStyles(makeStyles);
  return <View style={[styles.card, style]} {...rest} />;
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      backgroundColor: t.colors.surface,
      borderWidth: 1,
      borderColor: t.colors.border,
      borderRadius: t.radius.card,
      padding: t.space.lg,
    },
  });
}
