import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { formatVoiceClock } from "../hooks/useVoiceRecorder";
import { colors, radius, sizes, spacing } from "../theme";
import type { VoicePhase } from "../types";
import { Text } from "./Text";

export function VoiceRecorder({
  phase,
  seconds,
  onStop,
  onCancel,
}: {
  phase: VoicePhase;
  seconds: number;
  onStop: () => void;
  onCancel: () => void;
}) {
  const processing = phase === "processing";
  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <View style={[styles.dot, processing && styles.dotMute]} />
        <Text style={styles.label}>
          {processing ? "Procesando audio…" : "Grabando…"}
        </Text>
        <Text style={styles.clock}>{formatVoiceClock(seconds)}</Text>
      </View>
      {processing ? (
        <ActivityIndicator color={colors.brand} />
      ) : (
        <View style={styles.actions}>
          <Pressable
            onPress={onCancel}
            accessibilityRole="button"
            accessibilityLabel="Cancelar grabación"
            style={styles.ghost}
          >
            <Text style={styles.ghostTxt}>Cancelar</Text>
          </Pressable>
          <Pressable
            onPress={onStop}
            accessibilityRole="button"
            accessibilityLabel="Detener y enviar"
            style={styles.stop}
          >
            <Text style={styles.stopTxt}>Detener</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    gap: spacing.md,
  },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.danger,
  },
  dotMute: { backgroundColor: colors.brand },
  label: { color: colors.text, fontWeight: "700", flex: 1 },
  clock: { color: colors.muted, fontVariant: ["tabular-nums"] },
  actions: { flexDirection: "row", gap: spacing.sm },
  ghost: {
    flex: 1,
    minHeight: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  ghostTxt: { color: colors.text, fontWeight: "600" },
  stop: {
    flex: 1,
    minHeight: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    backgroundColor: colors.brand,
  },
  stopTxt: { color: colors.onBrand, fontWeight: "700" },
});
