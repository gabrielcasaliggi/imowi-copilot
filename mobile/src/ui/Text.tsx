import {
  Text as RNText,
  StyleSheet,
  type StyleProp,
  type TextProps,
  type TextStyle,
} from "react-native";

import { withManrope } from "../theme/fonts";
import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { textRoles } from "../theme/typography";

/** Tope de escalado de la letra del sistema (accesibilidad sin romper el layout). */
export const MAX_FONT_SCALE = 1.3;

type Variant =
  | "kicker"
  | "label"
  | "meta"
  | "body"
  | "subtitle"
  | "section"
  | "greeting"
  | "title"
  | "heading"
  | "error";

export function Text({
  variant = "body",
  style,
  maxFontSizeMultiplier = MAX_FONT_SCALE,
  ...rest
}: TextProps & { variant?: Variant; style?: StyleProp<TextStyle> }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <RNText
      style={withManrope([styles[variant], style])}
      maxFontSizeMultiplier={maxFontSizeMultiplier}
      {...rest}
    />
  );
}

function makeStyles(t: Theme) {
  const { ink, muted, danger } = t.colors;
  return StyleSheet.create({
    kicker: { ...textRoles.kicker, color: muted },
    label: { ...textRoles.label, color: muted },
    meta: { ...textRoles.meta, color: muted },
    body: { ...textRoles.body, color: ink },
    subtitle: { ...textRoles.subtitle, color: muted },
    section: { ...textRoles.section, color: muted },
    greeting: { ...textRoles.greeting, color: ink },
    title: { ...textRoles.title, color: ink },
    heading: { ...textRoles.heading, color: ink },
    error: { ...textRoles.error, color: danger },
  });
}
