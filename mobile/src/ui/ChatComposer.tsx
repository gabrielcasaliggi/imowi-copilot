import Ionicons from "@expo/vector-icons/Ionicons";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import { withManrope } from "../theme/fonts";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { MAX_FONT_SCALE } from "./Text";

const ICON = 22;

export function ChatComposer({
  value,
  onChangeText,
  onSend,
  onMic,
  busy,
  voiceBusy,
  placeholder,
  paddingBottom,
}: {
  value: string;
  onChangeText: (v: string) => void;
  onSend: () => void;
  onMic: () => void;
  busy: boolean;
  voiceBusy: boolean;
  placeholder: string;
  paddingBottom: number;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const locked = busy || voiceBusy;
  const sendOff = locked || !value.trim();
  return (
    <View style={[styles.composer, { paddingBottom }]}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        selectionColor={colors.primary}
        cursorColor={colors.primary}
        maxFontSizeMultiplier={MAX_FONT_SCALE}
        style={withManrope(styles.input)}
        editable={!locked}
        onSubmitEditing={() => {
          if (!sendOff) onSend();
        }}
        returnKeyType="send"
        blurOnSubmit
        multiline
        maxLength={4000}
        accessibilityLabel="Mensaje"
      />
      <Pressable
        onPress={onMic}
        disabled={locked}
        accessibilityRole="button"
        accessibilityLabel="Mensaje de voz"
        accessibilityState={{ disabled: locked }}
        style={[styles.micBtn, locked && styles.btnDisabled]}
      >
        <Ionicons
          name="mic"
          size={ICON}
          color={locked ? colors.onDisabled : colors.primary}
          allowFontScaling={false}
        />
      </Pressable>
      <Pressable
        onPress={onSend}
        disabled={sendOff}
        accessibilityRole="button"
        accessibilityLabel="Enviar"
        accessibilityState={{ disabled: sendOff }}
        style={[styles.sendBtn, sendOff && styles.btnDisabled]}
      >
        {busy ? (
          <ActivityIndicator color={colors.onDisabled} />
        ) : (
          <Ionicons
            name="send"
            size={ICON - 2}
            color={sendOff ? colors.onDisabled : colors.onPrimary}
            allowFontScaling={false}
          />
        )}
      </Pressable>
    </View>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, radius, size, fontSize } = t;
  return StyleSheet.create({
    composer: {
      flexDirection: "row",
      alignItems: "flex-end",
      gap: space.sm,
      paddingTop: space.md,
      borderTopWidth: 1,
      borderTopColor: colors.border,
    },
    input: {
      flex: 1,
      backgroundColor: colors.surface,
      borderColor: colors.borderStrong,
      borderWidth: 1,
      borderRadius: radius.pill,
      color: colors.ink,
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      fontSize: fontSize.base,
      lineHeight: 20,
      minHeight: size.hit,
      maxHeight: 120,
    },
    micBtn: {
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.pill,
      minHeight: size.hit,
      minWidth: size.hit,
      alignItems: "center",
      justifyContent: "center",
    },
    sendBtn: {
      backgroundColor: colors.primary,
      borderRadius: radius.pill,
      width: size.hit,
      height: size.hit,
      alignItems: "center",
      justifyContent: "center",
    },
    // Deshabilitado: fondo gris y contenido onDisabled (≥ 3:1), sin opacidad que lo haga ilegible.
    btnDisabled: { backgroundColor: colors.disabled, borderColor: colors.disabled },
  });
}
