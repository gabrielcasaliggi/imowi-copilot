import { Pressable, StyleSheet, View } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { Text } from "./Text";

type Tone = "warning" | "ok";

export function Banner({
  children,
  tone = "warning",
  onPress,
  actionLabel,
}: {
  children: string;
  tone?: Tone;
  onPress?: () => void;
  actionLabel?: string;
}) {
  const styles = useThemedStyles(makeStyles);
  const body = (
    <View style={[styles.base, tone === "ok" ? styles.ok : styles.warning]}>
      <Text style={[styles.copy, tone === "ok" ? styles.copyOk : styles.copyWarn]}>
        {children}
      </Text>
      {actionLabel ? (
        <Text style={[styles.action, tone === "ok" ? styles.copyOk : styles.copyWarn]}>
          {actionLabel}
        </Text>
      ) : null}
    </View>
  );
  if (onPress) {
    return (
      <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={actionLabel || children}>
        {body}
      </Pressable>
    );
  }
  return body;
}

function makeStyles(t: Theme) {
  const { colors, space, radius, fontSize } = t;
  return StyleSheet.create({
    base: {
      borderWidth: 1,
      borderRadius: radius.control,
      padding: space.md,
      marginBottom: space.sm,
    },
    warning: { backgroundColor: colors.warnSoft, borderColor: colors.warn },
    ok: { backgroundColor: colors.okSoft, borderColor: colors.ok },
    copy: { fontSize: fontSize.sm, lineHeight: 20 },
    copyWarn: { color: colors.warn },
    copyOk: { color: colors.ok },
    action: { marginTop: space.sm, fontWeight: "700", fontSize: fontSize.sm },
  });
}
