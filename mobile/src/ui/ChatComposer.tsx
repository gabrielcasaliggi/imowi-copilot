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
  busy,
  placeholder,
  paddingBottom,
}: {
  value: string;
  onChangeText: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  placeholder: string;
  paddingBottom: number;
}) {
  const disabled = busy || !value.trim();
  return (
    <View style={[styles.composer, { paddingBottom }]}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={styles.input}
        editable={!busy}
        onSubmitEditing={() => {
          if (!disabled) onSend();
        }}
        returnKeyType="send"
        blurOnSubmit
        multiline
        maxLength={4000}
        accessibilityLabel="Mensaje"
      />
      <Pressable
        onPress={onSend}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="Enviar"
        accessibilityState={{ disabled }}
        style={[styles.sendBtn, disabled && styles.off]}
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
