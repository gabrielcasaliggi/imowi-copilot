import { StyleSheet, View } from "react-native";

import { spacing } from "../theme";
import { Button } from "./Button";
import { Text } from "./Text";
import { TextField } from "./TextField";

export function PinSetup({
  pin,
  onChangePin,
  onSave,
  onSkip,
  busy,
  error,
  skipLabel = "Omitir por ahora",
  title = "Creá un PIN",
}: {
  pin: string;
  onChangePin: (v: string) => void;
  onSave: () => void;
  onSkip?: () => void;
  busy: boolean;
  error: string;
  skipLabel?: string;
  title?: string;
}) {
  return (
    <View>
      <Text variant="title">{title}</Text>
      <Text variant="subtitle" style={styles.sub}>
        Para entrar de nuevo sin código al email. 6 a 8 dígitos.
      </Text>
      <TextField
        value={pin}
        onChangeText={onChangePin}
        keyboardType="number-pad"
        secureTextEntry
        placeholder="6–8 dígitos"
        editable={!busy}
        maxLength={8}
        accessibilityLabel="PIN"
      />
      <Button
        label={busy ? "Guardando…" : "Guardar PIN"}
        onPress={onSave}
        disabled={busy || pin.length < 6}
        loading={busy}
      />
      {onSkip ? (
        <Button variant="ghost" label={skipLabel} onPress={onSkip} disabled={busy} />
      ) : null}
      {error ? <Text variant="error" style={styles.err}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sub: { marginBottom: spacing.lg, marginTop: spacing.sm },
  err: { marginTop: spacing.sm },
});
