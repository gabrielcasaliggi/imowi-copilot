import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from "react-native";

import { useTickets } from "../hooks/useTickets";
import { formatTicketWhen, labelTicketEstado, present } from "../present";
import { colors, layout, spacing } from "../theme";
import type { InboxConversation, PortalTicket } from "../types";
import { Banner } from "../ui/Banner";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Screen } from "../ui/Screen";
import { Text } from "../ui/Text";
import { TicketCard } from "../ui/TicketCard";

function estadoActividad(estado: string): string {
  if (estado === "espera_agente") return "Estás en espera de un agente.";
  if (estado === "con_agente") return "Un agente está en este chat.";
  if (estado === "cerrado") return "La conversación está cerrada.";
  return "";
}

export function ActivityScreen({
  conv,
  token,
  onExit,
  onGoEko,
}: {
  conv: InboxConversation;
  token: string;
  onExit: () => void;
  onGoEko: () => void;
}) {
  const {
    items,
    loading,
    refreshing,
    error,
    refresh,
    detail,
    detailBusy,
    openDetail,
    closeDetail,
  } = useTickets({ token, onAuthExpired: onExit });

  const [selectedId, setSelectedId] = useState("");
  const handoff = estadoActividad(conv.estado);
  const canOpenEko =
    Boolean(detail?.ticket.conversacion_id) &&
    detail?.ticket.conversacion_id === conv.id;

  const onSelect = (item: PortalTicket) => {
    if (selectedId === item.id && detail?.ticket.id === item.id) {
      setSelectedId("");
      closeDetail();
      return;
    }
    setSelectedId(item.id);
    void openDetail(item.id);
  };

  return (
    <Screen safeBottom={false}>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            tintColor={colors.brand}
            colors={[colors.brand]}
          />
        }
        contentContainerStyle={[
          styles.scroll,
          items.length === 0 && !loading ? styles.grow : null,
        ]}
        ListHeaderComponent={
          <View style={styles.header}>
            <Text variant="heading" style={styles.title}>Actividad</Text>
            <Text variant="subtitle" style={styles.lead}>
              Tus tickets y el estado de esta conversación.
            </Text>
            {handoff ? (
              <Banner
                tone={conv.estado === "con_agente" ? "ok" : "warning"}
                onPress={onGoEko}
                actionLabel="Ir a Eko"
              >
                {handoff}
              </Banner>
            ) : null}
            {error ? (
              <Text variant="error" style={styles.err}>{error}</Text>
            ) : null}
            {loading ? (
              <View style={styles.loading}>
                <ActivityIndicator color={colors.brand} />
                <Text variant="meta">Cargando tickets…</Text>
              </View>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          loading ? null : (
            <EmptyState
              title="No tenés tickets"
              description="Cuando Eko derive un caso a un ticket, vas a verlo acá con su estado."
            />
          )
        }
        renderItem={({ item }) => (
          <View style={styles.item}>
            <TicketCard
              item={item}
              selected={selectedId === item.id}
              busy={detailBusy && selectedId === item.id}
              onPress={() => onSelect(item)}
            />
            {detail && detail.ticket.id === item.id ? (
              <Card style={styles.detail}>
                <Text variant="label">Detalle</Text>
                <Text variant="meta" style={styles.detailLine}>
                  Estado: {labelTicketEstado(detail.ticket.estado)}
                </Text>
                {present(detail.ticket.origen) ? (
                  <Text variant="meta" style={styles.detailLine}>
                    Origen: {detail.ticket.origen}
                  </Text>
                ) : null}
                {formatTicketWhen(detail.ticket.created_at) ? (
                  <Text variant="meta" style={styles.detailLine}>
                    Creado {formatTicketWhen(detail.ticket.created_at)}
                  </Text>
                ) : null}
                {detail.eventos.length > 0 ? (
                  <View style={styles.events}>
                    <Text variant="label">Novedades</Text>
                    {detail.eventos.map((ev) => (
                      <View key={ev.id} style={styles.event}>
                        <Text style={styles.eventTitle}>
                          {present(ev.titulo) || "Actualización"}
                        </Text>
                        {present(ev.detalle) ? (
                          <Text variant="meta">{ev.detalle}</Text>
                        ) : null}
                        {formatTicketWhen(ev.created_at) ? (
                          <Text variant="meta">{formatTicketWhen(ev.created_at)}</Text>
                        ) : null}
                      </View>
                    ))}
                  </View>
                ) : (
                  <Text variant="meta" style={styles.detailLine}>
                    No hay novedades visibles para este ticket.
                  </Text>
                )}
                {canOpenEko ? (
                  <Pressable
                    onPress={onGoEko}
                    accessibilityRole="button"
                    accessibilityLabel="Ver conversación en Eko"
                    style={styles.linkBtn}
                  >
                    <Text style={styles.linkTxt}>Ver conversación en Eko</Text>
                  </Pressable>
                ) : null}
                <Pressable
                  onPress={() => {
                    setSelectedId("");
                    closeDetail();
                  }}
                  accessibilityRole="button"
                  accessibilityLabel="Cerrar detalle"
                  style={styles.closeBtn}
                >
                  <Text style={styles.closeTxt}>Cerrar detalle</Text>
                </Pressable>
              </Card>
            ) : null}
          </View>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xl,
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
  },
  grow: { flexGrow: 1 },
  header: { marginBottom: spacing.md, gap: spacing.sm },
  title: { marginBottom: spacing.xs },
  lead: { marginBottom: spacing.md },
  err: { marginBottom: spacing.sm },
  loading: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.md,
  },
  item: { marginBottom: spacing.md, gap: spacing.sm },
  detail: { gap: spacing.xs },
  detailLine: { marginTop: spacing.xs },
  events: { marginTop: spacing.md, gap: spacing.sm },
  event: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.sm,
    gap: 4,
  },
  eventTitle: { color: colors.text, fontWeight: "600" },
  linkBtn: {
    marginTop: spacing.md,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    backgroundColor: colors.brand,
  },
  linkTxt: { color: colors.onBrand, fontWeight: "700" },
  closeBtn: {
    marginTop: spacing.sm,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  closeTxt: { color: colors.muted, fontWeight: "600" },
});
