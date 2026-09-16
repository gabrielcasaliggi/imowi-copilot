import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import { colors, radius, sizes, spacing } from "../theme";
import { Text } from "./Text";

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
  const locked = busy || voiceBusy;
  const sendOff = locked || !value.trim();
  return (
    <View style={[styles.composer, { paddingBottom }]}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={styles.input}
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
        style={[styles.micBtn, locked && styles.off]}
      >
        <View style={styles.micGlyph} />
      </Pressable>
      <Pressable
        onPress={onSend}
        disabled={sendOff}
        accessibilityRole="button"
        accessibilityLabel="Enviar"
        accessibilityState={{ disabled: sendOff }}
        style={[styles.sendBtn, sendOff && styles.off]}
      >
        {busy ? (
          <ActivityIndicator color={colors.onBrand} />
        ) : (
          <Text style={styles.sendTxt}>Enviar</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  input: {
    flex: 1,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.xl,
    color: colors.text,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: 15,
    lineHeight: 20,
    minHeight: sizes.hit,
    maxHeight: 120,
  },
  micBtn: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.full,
    minHeight: sizes.hit,
    minWidth: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
  },
  micGlyph: {
    width: 12,
    height: 18,
    borderRadius: 6,
    backgroundColor: colors.brand,
  },
  sendBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.full,
    paddingHorizontal: spacing.lg,
    minHeight: sizes.hit,
    minWidth: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
  },
  off: { opacity: 0.45 },
  sendTxt: { color: colors.onBrand, fontWeight: "700" },
});
