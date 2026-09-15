import {
  Text as RNText,
  StyleSheet,
  type StyleProp,
  type TextProps,
  type TextStyle,
} from "react-native";

import { colors, typography } from "../theme";

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
  ...rest
}: TextProps & { variant?: Variant; style?: StyleProp<TextStyle> }) {
  return <RNText style={[styles[variant], style]} {...rest} />;
}

const styles = StyleSheet.create({
  kicker: { ...typography.kicker, color: colors.muted },
  label: { ...typography.label, color: colors.muted },
  meta: { ...typography.meta, color: colors.muted },
  body: { ...typography.body, color: colors.text },
  subtitle: { ...typography.subtitle, color: colors.muted },
  section: { ...typography.section, color: colors.muted },
  greeting: { ...typography.greeting, color: colors.text },
  title: { ...typography.title, color: colors.text },
  heading: { ...typography.heading, color: colors.text },
  error: { fontSize: 13, color: colors.danger },
});
