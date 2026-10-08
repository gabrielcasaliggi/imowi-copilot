import { Linking, StyleSheet, Text, type StyleProp, type TextStyle } from "react-native";

import { withManrope } from "../theme/fonts";
import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { MAX_FONT_SCALE } from "./Text";

const URL_RE = /(https?:\/\/[^\s<>"']+)/gi;

function cleanUrl(raw: string): string {
  return raw.replace(/[.,;:!?)]+$/g, "");
}

type Part = { type: "text" | "url"; value: string };

function splitParts(texto: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  const re = new RegExp(URL_RE.source, URL_RE.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(texto)) !== null) {
    if (m.index > last) {
      parts.push({ type: "text", value: texto.slice(last, m.index) });
    }
    const url = cleanUrl(m[0]);
    parts.push({ type: "url", value: url });
    const trailing = m[0].slice(url.length);
    if (trailing) parts.push({ type: "text", value: trailing });
    last = m.index + m[0].length;
  }
  if (last < texto.length) {
    parts.push({ type: "text", value: texto.slice(last) });
  }
  return parts.length ? parts : [{ type: "text", value: texto }];
}

export function MessageText({
  texto,
  style,
  linkStyle,
}: {
  texto: string;
  style?: StyleProp<TextStyle>;
  linkStyle?: StyleProp<TextStyle>;
}) {
  const styles = useThemedStyles(makeStyles);
  const parts = splitParts(texto || "");
  return (
    <Text style={withManrope(style)} maxFontSizeMultiplier={MAX_FONT_SCALE}>
      {parts.map((p, i) =>
        p.type === "url" ? (
          <Text
            key={`${i}-${p.value}`}
            style={withManrope([style, styles.link, linkStyle])}
            onPress={() => {
              void Linking.openURL(p.value).catch(() => {});
            }}
          >
            {p.value}
          </Text>
        ) : (
          <Text key={`${i}-t`}>{p.value}</Text>
        ),
      )}
    </Text>
  );
}

function makeStyles(t: Theme) {
  const { colors } = t;
  return StyleSheet.create({
    link: {
      color: colors.primary,
      textDecorationLine: "underline",
      fontWeight: "600",
    },
  });
}
