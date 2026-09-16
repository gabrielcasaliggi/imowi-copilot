import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import {
  connectivityTone,
  formatConnectivityEta,
  labelConnectivityStatus,
  present,
} from "../present";
import { colors, radius, sizes, spacing } from "../theme";
import type { ConnectivityStatusResponse } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { Text } from "./Text";

export function ConnectivityCard({
  data,
  loading,
  error,
  onRetry,
  onAskEko,
  onSelectService,
}: {
  data: ConnectivityStatusResponse | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onAskEko: (texto: string | null) => void;
  onSelectService: (serviceId: string) => void;
}) {
  if (loading && !data) {
    return (
      <Card accessibilityLabel="Consultando estado de Internet">
        <Text variant="label">Estado de Internet</Text>
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.brand} />
          <Text variant="meta" style={styles.loadingText}>
            Verificando tu acceso…
          </Text>
        </View>
      </Card>
    );
  }

  if (error && !data) {
    return (
      <Card accessibilityLabel="No se pudo consultar el estado de Internet">
        <Text variant="label">Estado de Internet</Text>
        <Text style={styles.errorBody}>{error}</Text>
        <Text variant="meta" style={styles.hint}>
          Esto no significa necesariamente que tu Internet esté caído.
        </Text>
        <View style={styles.row}>
          <Button
            label="Reintentar"
            variant="ghost"
            onPress={onRetry}
            accessibilityHint="Vuelve a consultar el estado"
            style={styles.flexBtn}
          />
          <Button
            label="Hablar con Eko"
            onPress={() => onAskEko(null)}
            accessibilityHint="Abre el chat con el asistente"
            style={styles.flexBtn}
          />
        </View>
      </Card>
    );
  }

  if (!data) return null;

  if (data.needs_service_selection && data.services?.length) {
    return (
      <Card accessibilityLabel="Elegí un servicio de Internet">
        <Text variant="label">Estado de Internet</Text>
        <Text style={styles.body}>{data.message}</Text>
        <View style={styles.services}>
          {data.services.map((s) => (
            <Pressable
              key={s.id}
              onPress={() => onSelectService(s.id)}
              accessibilityRole="button"
              accessibilityLabel={s.label}
              accessibilityHint="Consultar el estado de este servicio"
              style={styles.serviceChip}
            >
              <Text style={styles.serviceChipLabel} numberOfLines={2}>
                {s.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </Card>
    );
  }

  const tone = connectivityTone(data.status);
  const headline = labelConnectivityStatus(data.status);
  const body = present(data.message);
  const eta = formatConnectivityEta(data.incident);
  const chatHint =
    present(data.actions?.chat_hint) ||
    "Si en tu casa sigue fallando, escribinos y te ayudamos.";
  const showCta = data.actions?.can_open_chat !== false;

  return (
    <Card
      accessibilityLabel={`Estado de Internet: ${headline}`}
      style={tone === "outage" ? styles.outageCard : undefined}
    >
      <Text variant="label">Estado de Internet</Text>
      {data.service?.label ? (
        <Text variant="meta" style={styles.serviceLabel} numberOfLines={2}>
          {data.service.label}
        </Text>
      ) : null}
      <Text
        variant="title"
        style={[
          styles.headline,
          tone === "ok" && styles.ok,
          tone === "warning" && styles.warn,
          tone === "outage" && styles.outage,
          tone === "neutral" && styles.neutral,
        ]}
        numberOfLines={3}
      >
        {headline}
      </Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
      {eta ? <Text variant="meta" style={styles.eta}>{eta}</Text> : null}
      {tone === "neutral" ? (
        <Text variant="meta" style={styles.hint}>
          No implica que tu servicio esté caído.
        </Text>
      ) : null}
      {showCta ? (
        <Button
          label={data.status === "operational" ? "Consultar con Eko" : "Hablar con Eko"}
          variant={data.status === "operational" ? "ghost" : "primary"}
          onPress={() =>
            onAskEko(
              data.status === "operational"
                ? "En la app figura que el acceso está bien, pero en mi casa no anda."
                : null,
            )
          }
          accessibilityHint={chatHint}
          style={styles.cta}
        />
      ) : null}
      {loading ? (
        <Text variant="meta" style={styles.refreshing}>
          Actualizando…
        </Text>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginTop: spacing.md,
    minHeight: sizes.hit,
  },
  loadingText: { flex: 1 },
  errorBody: { marginTop: spacing.sm, color: colors.text },
  hint: { marginTop: spacing.sm },
  row: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  flexBtn: { flex: 1 },
  services: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  serviceChip: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: sizes.hit,
    minWidth: "47%",
    flexGrow: 1,
    justifyContent: "center",
  },
  serviceChipLabel: { color: colors.text, fontWeight: "600", fontSize: 15 },
  serviceLabel: { marginTop: spacing.xs },
  headline: { marginTop: spacing.sm, marginBottom: spacing.xs },
  ok: { color: colors.online },
  warn: { color: colors.amber },
  outage: { color: colors.danger },
  neutral: { color: colors.muted },
  body: { color: colors.text, fontSize: 15, lineHeight: 22 },
  eta: { marginTop: spacing.sm },
  cta: { marginTop: spacing.md },
  refreshing: { marginTop: spacing.sm },
  outageCard: {
    borderColor: "rgba(248,113,113,0.35)",
  },
});
