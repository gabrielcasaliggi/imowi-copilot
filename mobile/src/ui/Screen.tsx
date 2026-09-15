import { StyleSheet, View, type ViewProps } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, spacing } from "../theme";

export function Screen({
  style,
  children,
  padded = true,
  safeBottom = true,
  ...rest
}: ViewProps & { padded?: boolean; safeBottom?: boolean }) {
  const insets = useSafeAreaInsets();
  const topPad = Math.max(insets.top, 12) + 8;
  const bottomPad = safeBottom ? Math.max(insets.bottom, 12) + 10 : spacing.md;
  return (
    <View
      style={[
        styles.root,
        { paddingTop: topPad, paddingBottom: bottomPad },
        padded && styles.padded,
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  padded: { paddingHorizontal: spacing.lg },
});
