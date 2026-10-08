import { useEffect, useMemo, useState } from "react";
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
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
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
  focusTicketId = "",
  focusSeq = 0,
  onFocusConsumed,
}: {
  conv: InboxConversation;
  token: string;
  onExit: () => void;
  onGoEko: () => void;
  /** Tras crear reclamo / push ticket: abrir detalle vía API auth. */
  focusTicketId?: string;
  /** Monotónico: re-abrir el mismo ticket_id en focuses sucesivos. */
  focusSeq?: number;
  onFocusConsumed?: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
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

  useEffect(() => {
    if (!focusSeq) return;
    const tid = (focusTicketId || "").trim();
    if (!tid) {
      onFocusConsumed?.();
      return;
    }
    setSelectedId(tid);
    refresh();
    void openDetail(tid)
      .then((ok) => {
        if (!ok) setSelectedId("");
      })
      .finally(() => {
        onFocusConsumed?.();
      });
    // Solo al llegar un focus nuevo (reclamo / push ticket).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional
  }, [focusSeq]);

  const listData = useMemo(() => {
    if (!detail?.ticket) return items;
    if (items.some((i) => i.id === detail.ticket.id)) return items;
    return [detail.ticket, ...items];
  }, [items, detail]);

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
        data={listData}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        contentContainerStyle={[
          styles.scroll,
          listData.length === 0 && !loading ? styles.grow : null,
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
                <ActivityIndicator color={colors.primary} />
                <Text variant="meta">Cargando tickets…</Text>
              </View>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          loading ? null : (
            <EmptyState
              title="No tenés tickets"
              description="Cuando generes un reclamo o Eko derive un caso, vas a verlo acá con su estado."
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
                  Ticket {detail.ticket.id}
                </Text>
                <Text variant="meta" style={styles.detailLine}>
                  Estado: {labelTicketEstado(detail.ticket.estado)}
                </Text>
                {present(detail.ticket.categoria) ? (
                  <Text variant="meta" style={styles.detailLine}>
                    Motivo: {detail.ticket.categoria}
                  </Text>
                ) : null}
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

function makeStyles(t: Theme) {
  const { colors, space, size, radius } = t;
  return StyleSheet.create({
    scroll: {
      paddingBottom: space.xl,
      width: "100%",
      maxWidth: size.maxContent,
      alignSelf: "center",
    },
    grow: { flexGrow: 1 },
    header: { marginBottom: space.md, gap: space.sm },
    title: { marginBottom: space.xs },
    lead: { marginBottom: space.md },
    err: { marginBottom: space.sm },
    loading: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm,
      paddingVertical: space.md,
    },
    item: { marginBottom: space.md, gap: space.sm },
    detail: { gap: space.xs },
    detailLine: { marginTop: space.xs },
    events: { marginTop: space.md, gap: space.sm },
    event: {
      borderTopWidth: 1,
      borderTopColor: colors.border,
      paddingTop: space.sm,
      gap: 4,
    },
    eventTitle: { color: colors.ink, fontWeight: "600" },
    linkBtn: {
      marginTop: space.md,
      minHeight: size.hit,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: radius.control,
      backgroundColor: colors.primary,
    },
    linkTxt: { color: colors.onPrimary, fontWeight: "700" },
    closeBtn: {
      marginTop: space.sm,
      minHeight: size.hit,
      alignItems: "center",
      justifyContent: "center",
    },
    closeTxt: { color: colors.muted, fontWeight: "600" },
  });
}
