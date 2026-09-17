import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";

import { colors, spacing } from "../theme";
import { Button } from "./Button";
import { Card } from "./Card";
import { Text } from "./Text";
import { TextField } from "./TextField";

export function CreateClaimForm({
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  error: string;
  onSubmit: (input: { motivo: string; descripcion: string }) => void;
  onCancel: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [descripcion, setDescripcion] = useState("");

  const askConfirm = () => {
    if (busy) return;
    const m = motivo.trim();
    const d = descripcion.trim();
    if (!m || !d) {
      Alert.alert(
        "Faltan datos",
        "Completá el motivo y una breve descripción del reclamo.",
      );
      return;
    }
    Alert.alert("¿Querés generar un reclamo?", undefined, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Crear reclamo",
        onPress: () => onSubmit({ motivo: m, descripcion: d }),
      },
    ]);
  };

  return (
    <Card accessibilityLabel="Crear reclamo">
      <Text variant="label">Crear reclamo</Text>
      <Text variant="meta" style={styles.lead}>
        Contanos qué necesitás. Un agente lo va a ver en la bandeja.
      </Text>
      <TextField
        label="Motivo"
        value={motivo}
        onChangeText={setMotivo}
        editable={!busy}
        maxLength={120}
        placeholder="Ej. Internet sin servicio"
        accessibilityLabel="Motivo del reclamo"
      />
      <TextField
        label="Descripción"
        value={descripcion}
        onChangeText={setDescripcion}
        editable={!busy}
        maxLength={2000}
        multiline
        numberOfLines={4}
        textAlignVertical="top"
        placeholder="Describí la situación con tus palabras"
        accessibilityLabel="Descripción del reclamo"
        style={styles.area}
      />
      {error ? (
        <Text variant="error" style={styles.err}>
          {error}
        </Text>
      ) : null}
      <View style={styles.row}>
        <Button
          label="Cancelar"
          variant="ghost"
          disabled={busy}
          onPress={onCancel}
          style={styles.flex}
        />
        <Button
          label="Crear reclamo"
          loading={busy}
          disabled={busy}
          onPress={askConfirm}
          style={styles.flex}
        />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  lead: { marginTop: spacing.xs, marginBottom: spacing.md },
  area: { minHeight: 96, paddingTop: spacing.md },
  err: { marginBottom: spacing.sm, color: colors.danger },
  row: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  flex: { flex: 1 },
});
