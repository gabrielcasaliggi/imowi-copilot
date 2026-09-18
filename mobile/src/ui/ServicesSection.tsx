import { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { present } from "../present";
import { colors, spacing } from "../theme";
import type { PortalServiceItem, PortalServiceType } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { Text } from "./Text";

const TYPE_ORDER: PortalServiceType[] = [
  "internet",
  "tv",
  "movil",
  "telefonia",
  "other",
];

const CANONICAL = new Set<string>(TYPE_ORDER);

export function typeTitle(type: PortalServiceType): string {
  if (type === "internet") return "Internet";
  if (type === "tv") return "TV";
  if (type === "movil") return "Móvil";
  if (type === "telefonia") return "Telefonía";
  return "Otros servicios";
}

export function servicesCountLabel(n: number): string {
  if (n <= 0) return "0 servicios";
  if (n === 1) return "1 servicio";
  return `${n} servicios`;
}

/** Últimos 4 dígitos de line_msisdn contractual; null si no hay dato. */
export function maskLineMsisdn(line: string | null | undefined): string | null {
  const digits = String(line || "").replace(/\D/g, "");
  if (digits.length !== 10) return null;
  return `····${digits.slice(-4)}`;
}

/** Agrupa para UI sin mutar ni filtrar el array del backend. */
export function groupServicesByType(
  items: PortalServiceItem[],
): { type: PortalServiceType; items: PortalServiceItem[] }[] {
  const buckets = new Map<PortalServiceType, PortalServiceItem[]>();
  for (const item of items) {
    const tip = (CANONICAL.has(item.type) ? item.type : "other") as PortalServiceType;
    const list = buckets.get(tip);
    if (list) list.push(item);
    else buckets.set(tip, [item]);
  }
  const out: { type: PortalServiceType; items: PortalServiceItem[] }[] = [];
  for (const tip of TYPE_ORDER) {
    const list = buckets.get(tip);
    if (list?.length) out.push({ type: tip, items: list });
  }
  return out;
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

function ServiceInstance({
  item,
  onViewConnectivity,
  onAskEko,
}: {
  item: PortalServiceItem;
  onViewConnectivity: (serviceId: string) => void;
  onAskEko: (texto: string | null) => void;
}) {
  const product = present(item.product);
  const label = present(item.label);
  const detail = product || label || "Servicio";
  const lineMasked =
    item.type === "movil" ? maskLineMsisdn(item.line_msisdn) : null;

  return (
    <View
      accessibilityLabel={`${detail}${lineMasked ? `, Línea ${lineMasked}` : ""}, ${adminStatus(item.active)}`}
      style={styles.instance}
    >
      <Text variant="title" style={styles.product} numberOfLines={3}>
        {detail}
      </Text>
      {lineMasked ? (
        <Text variant="meta" style={styles.meta}>
          Línea {lineMasked}
        </Text>
      ) : null}
      <Text variant="meta" style={styles.meta}>
        {item.active ? "Activo" : "No activo"}
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
    </View>
  );
}

function ServiceTypeGroup({
  type,
  items,
  expanded,
  onToggle,
  onViewConnectivity,
  onAskEko,
}: {
  type: PortalServiceType;
  items: PortalServiceItem[];
  expanded: boolean;
  onToggle: () => void;
  onViewConnectivity: (serviceId: string) => void;
  onAskEko: (texto: string | null) => void;
}) {
  const title = typeTitle(type);
  const activeN = items.filter((i) => i.active).length;
  const summary =
    activeN === items.length
      ? `${servicesCountLabel(items.length)} activos`
      : `${servicesCountLabel(items.length)} · ${activeN} activos`;

  return (
    <Card style={styles.groupCard}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        accessibilityLabel={`${title}, ${summary}`}
        accessibilityHint={expanded ? "Ocultar detalle" : "Ver servicios de este tipo"}
        style={styles.groupHeader}
      >
        <View style={styles.groupHeaderText}>
          <Text variant="title" style={styles.groupTitle}>
            {title}
          </Text>
          <Text variant="meta" style={styles.meta}>
            {summary}
          </Text>
        </View>
        <Text variant="meta" style={styles.chevron}>
          {expanded ? "▾" : "›"}
        </Text>
      </Pressable>
      {expanded ? (
        <View style={styles.instances}>
          <Text variant="meta" style={styles.hint}>
            Dato administrativo de tu cuenta. No es un diagnóstico técnico.
          </Text>
          {items.map((item) => (
            <ServiceInstance
              key={item.id}
              item={item}
              onViewConnectivity={onViewConnectivity}
              onAskEko={onAskEko}
            />
          ))}
        </View>
      ) : null}
    </Card>
  );
}

export function ServicesSection({
  items,
  loading,
  error,
  unavailable,
  onRetry,
  onViewConnectivity,
  onAskEko,
}: {
  items: PortalServiceItem[];
  loading: boolean;
  error: string;
  unavailable: boolean;
  onRetry: () => void;
  onViewConnectivity: (serviceId: string) => void;
  onAskEko: (texto: string | null) => void;
}) {
  const groups = useMemo(() => groupServicesByType(items), [items]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggle = (type: PortalServiceType) => {
    setExpanded((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const expandAll = () => {
    const next: Record<string, boolean> = {};
    for (const g of groups) next[g.type] = true;
    setExpanded(next);
  };

  const allExpanded =
    groups.length > 0 && groups.every((g) => expanded[g.type]);

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
      {groups.map((g) => (
        <ServiceTypeGroup
          key={g.type}
          type={g.type}
          items={g.items}
          expanded={Boolean(expanded[g.type])}
          onToggle={() => toggle(g.type)}
          onViewConnectivity={onViewConnectivity}
          onAskEko={onAskEko}
        />
      ))}
      {groups.length > 1 && !allExpanded ? (
        <Button
          label="Ver todos"
          variant="ghost"
          onPress={expandAll}
          accessibilityHint="Expande todos los tipos de servicio"
          style={styles.cta}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  groupCard: { marginBottom: spacing.sm },
  groupHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    minHeight: 44,
  },
  groupHeaderText: { flex: 1, gap: spacing.xs },
  groupTitle: { fontSize: 18 },
  chevron: { fontSize: 22, color: colors.muted, paddingHorizontal: spacing.xs },
  instances: {
    marginTop: spacing.md,
    gap: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  instance: {
    gap: spacing.xs,
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  product: { fontSize: 17 },
  meta: { marginTop: spacing.xs },
  hint: { marginTop: spacing.xs },
  cta: { marginTop: spacing.sm },
  loading: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 44,
  },
  err: { color: colors.text },
});
