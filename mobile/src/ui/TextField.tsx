import { useState } from "react";
import {
  StyleSheet,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";

import { withManrope } from "../theme/fonts";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { MAX_FONT_SCALE, Text } from "./Text";

export function TextField({
  label,
  style,
  onFocus,
  onBlur,
  maxFontSizeMultiplier = MAX_FONT_SCALE,
  ...rest
}: TextInputProps & { label?: string }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.wrap}>
      {label ? <Text variant="label" style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.muted}
        selectionColor={colors.primary}
        cursorColor={colors.primary}
        maxFontSizeMultiplier={maxFontSizeMultiplier}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        style={withManrope([styles.input, focused && styles.inputFocused, style])}
        {...rest}
      />
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: { marginBottom: t.space.md },
    label: { marginBottom: t.space.sm },
    input: {
      backgroundColor: t.colors.surface,
      borderColor: t.colors.borderStrong,
      borderWidth: 1,
      borderRadius: t.radius.control,
      color: t.colors.ink,
      paddingHorizontal: t.space.lg,
      paddingVertical: t.space.md,
      fontSize: t.fontSize.lg,
      minHeight: t.size.hit,
    },
    inputFocused: { borderColor: t.colors.primary },
  });
}
