import { StyleSheet, View, type ViewProps } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { space } from "../theme/tokens";

export function Screen({
  style,
  children,
  padded = true,
  safeBottom = true,
  ...rest
}: ViewProps & { padded?: boolean; safeBottom?: boolean }) {
  const insets = useSafeAreaInsets();
  const styles = useThemedStyles(makeStyles);
  const topPad = Math.max(insets.top, space.md) + space.sm;
  const bottomPad = safeBottom ? Math.max(insets.bottom, space.md) + space.md : space.md;
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

function makeStyles(t: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: t.colors.bg },
    padded: { paddingHorizontal: t.space.lg },
  });
}
