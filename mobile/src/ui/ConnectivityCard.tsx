import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import {
  connectivityTone,
  formatConnectivityEta,
  labelConnectivityStatus,
  present,
} from "../present";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import type { ConnectivityStatusResponse } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { StatusRing } from "./StatusRing";
import { Text } from "./Text";

export function ConnectivityCard({
  data,
  loading,
  error,
  onRetry,
  onAskEko,
  onSelectService,
  onCreateClaim,
}: {
  data: ConnectivityStatusResponse | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onAskEko: (texto: string | null) => void;
  onSelectService: (serviceId: string) => void;
  /** Acción explícita: no crea ticket solo. */
  onCreateClaim?: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  if (loading && !data) {
    return (
      <Card accessibilityLabel="Consultando estado de Internet">
        <Text variant="label">Estado de Internet</Text>
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.primary} />
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
      <View style={styles.statusRow}>
        <StatusRing tone={tone} />
        <View style={styles.statusText}>
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
        </View>
      </View>
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
      {onCreateClaim ? (
        <Button
          label="Crear reclamo"
          variant="ghost"
          onPress={onCreateClaim}
          accessibilityHint="Abrí el formulario para generar un reclamo"
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

function makeStyles(t: Theme) {
  const { colors, space, radius, size, fontSize } = t;
  return StyleSheet.create({
    loadingRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.md,
      marginTop: space.md,
      minHeight: size.hit,
    },
    loadingText: { flex: 1 },
    errorBody: { marginTop: space.sm, color: colors.ink },
    hint: { marginTop: space.sm },
    row: { flexDirection: "row", gap: space.sm, marginTop: space.md },
    flexBtn: { flex: 1 },
    services: {
      flexDirection: "row",
      flexWrap: "wrap",
      gap: space.sm,
      marginTop: space.md,
    },
    serviceChip: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.control,
      paddingVertical: space.md,
      paddingHorizontal: space.lg,
      minHeight: size.hit,
      minWidth: "47%",
      flexGrow: 1,
      justifyContent: "center",
    },
    serviceChipLabel: { color: colors.ink, fontWeight: "600", fontSize: fontSize.base },
    statusRow: { flexDirection: "row", alignItems: "center", gap: space.md },
    statusText: { flex: 1 },
    serviceLabel: { marginTop: space.xs },
    headline: { marginTop: space.sm, marginBottom: space.xs },
    ok: { color: colors.ok },
    warn: { color: colors.warn },
    outage: { color: colors.danger },
    neutral: { color: colors.muted },
    body: { color: colors.ink, fontSize: fontSize.base, lineHeight: 22 },
    eta: { marginTop: space.sm },
    cta: { marginTop: space.md },
    refreshing: { marginTop: space.sm },
    outageCard: {
      borderColor: colors.danger,
    },
  });
}
