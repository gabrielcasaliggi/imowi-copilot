import { ActivityIndicator, StyleSheet, View } from "react-native";

import { present } from "../present";
import { colors, spacing } from "../theme";
import type { PortalServiceItem, PortalServiceType } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { Text } from "./Text";

function typeTitle(type: PortalServiceType): string {
  if (type === "internet") return "Internet";
  if (type === "tv") return "TV";
  if (type === "movil") return "Móvil";
  if (type === "telefonia") return "Telefonía";
  return "Otros servicios";
}

function adminStatus(active: boolean): string {
  return active ? "Activo" : "No activo";
}

function ekoPrompt(type: PortalServiceType): string {
  if (type === "tv") return "Tengo una consulta sobre mi TV / Sensa.";
  if (type === "movil") return "Tengo una consulta sobre mi línea móvil.";
  if (type === "telefonia") return "Tengo una consulta sobre mi telefonía fija.";
  return "Tengo una consulta sobre un servicio de mi cuenta.";
}

export const WIFI_CHANGE_PROMPT =
  "Quiero cambiar la contraseña o el nombre de mi Wi-Fi.";

function ServiceRow({
  item,
  fallbackMsisdn,
  onViewConnectivity,
  onAskEko,
}: {
  item: PortalServiceItem;
  fallbackMsisdn?: string;
  onViewConnectivity: (serviceId: string) => void;
  onAskEko: (texto: string | null) => void;
}) {
  const product = present(item.product);
  const label = present(item.label);
  const detail = product || label;
  const line = present(item.msisdn) || present(fallbackMsisdn);
  const showMsisdn = item.type === "movil" && line;

  return (
    <Card
      accessibilityLabel={`${typeTitle(item.type)}, ${detail || "servicio"}, ${adminStatus(item.active)}`}
      style={styles.card}
    >
      <Text variant="label">{typeTitle(item.type)}</Text>
      {detail ? (
        <Text variant="title" style={styles.product} numberOfLines={3}>
          {detail}
        </Text>
      ) : null}
      {showMsisdn ? (
        <Text variant="meta" style={styles.meta}>
          Línea {line}
        </Text>
      ) : null}
      <Text variant="meta" style={styles.meta}>
        {item.active ? "Contratado · Activo" : "Contratado · No activo"}
      </Text>
      <Text variant="meta" style={styles.hint}>
        Dato administrativo de tu cuenta. No es un diagnóstico técnico.
      </Text>
      {item.type === "internet" ? (
        <>
          <Button
            label="Ver estado"
            variant="ghost"
            onPress={() => onViewConnectivity(item.id)}
            accessibilityHint="Consulta el estado de Internet de este servicio"
            style={styles.cta}
          />
          <Button
            label="Cambiar Wi-Fi"
            variant="ghost"
            onPress={() => onAskEko(WIFI_CHANGE_PROMPT)}
            accessibilityHint="Abre Eko para cambiar la contraseña o el nombre del Wi-Fi"
            style={styles.cta}
          />
        </>
      ) : (
        <Button
          label="Consultar con Eko"
          variant="ghost"
          onPress={() => onAskEko(ekoPrompt(item.type))}
          accessibilityHint="Abre el chat con el asistente"
          style={styles.cta}
        />
      )}
    </Card>
  );
}

export function ServicesSection({
  items,
  loading,
  error,
  unavailable,
  msisdn,
  onRetry,
  onViewConnectivity,
  onAskEko,
}: {
  items: PortalServiceItem[];
  loading: boolean;
  error: string;
  unavailable: boolean;
  msisdn?: string;
  onRetry: () => void;
  onViewConnectivity: (serviceId: string) => void;
  onAskEko: (texto: string | null) => void;
}) {
  return (
    <View style={styles.wrap}>
      <SectionHeader title="Tus servicios" />
      {loading && items.length === 0 ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.brand} />
          <Text variant="meta">Cargando servicios…</Text>
        </View>
      ) : null}
      {error ? (
        <Card>
          <Text style={styles.err}>{error}</Text>
          <Text variant="meta" style={styles.hint}>
            No implica que no tengas servicios contratados.
          </Text>
          <Button
            label="Reintentar"
            variant="ghost"
            onPress={onRetry}
            style={styles.cta}
          />
        </Card>
      ) : null}
      {!error && unavailable ? (
        <Card>
          <Text>
            No pudimos consultar el padrón de servicios ahora.
          </Text>
          <Button
            label="Reintentar"
            variant="ghost"
            onPress={onRetry}
            style={styles.cta}
          />
        </Card>
      ) : null}
      {!error && !unavailable && !loading && items.length === 0 ? (
        <Card>
          <Text>No encontramos servicios asociados a tu cuenta.</Text>
        </Card>
      ) : null}
      {items.map((item) => (
        <ServiceRow
          key={item.id}
          item={item}
          fallbackMsisdn={msisdn}
          onViewConnectivity={onViewConnectivity}
          onAskEko={onAskEko}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  card: { marginBottom: spacing.sm },
  product: { marginTop: spacing.xs, fontSize: 18 },
  meta: { marginTop: spacing.xs },
  hint: { marginTop: spacing.xs },
  cta: { marginTop: spacing.md },
  loading: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 44,
  },
  err: { color: colors.text },
});
