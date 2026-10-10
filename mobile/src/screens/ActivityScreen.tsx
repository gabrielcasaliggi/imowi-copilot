import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  BackHandler,
  FlatList,
  RefreshControl,
  StyleSheet,
  View,
} from "react-native";

import { useTickets } from "../hooks/useTickets";
import { useTabScrollBottomPadding } from "../navigation/tabBar";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import type { InboxConversation } from "../types";
import { Banner } from "../ui/Banner";
import { EmptyState } from "../ui/EmptyState";
import { Screen } from "../ui/Screen";
import { Text } from "../ui/Text";
import { TicketCard } from "../ui/TicketCard";
import { TicketDetailScreen } from "./TicketDetailScreen";

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
  /** Tras crear reclamo / push ticket: abrir el detalle de ese reclamo. */
  focusTicketId?: string;
  /** Monotónico: re-abrir el mismo ticket_id en focuses sucesivos. */
  focusSeq?: number;
  onFocusConsumed?: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const { items, loading, refreshing, error, refresh } = useTickets({
    token,
    onAuthExpired: onExit,
  });

  // Detalle por estado interno: "" = lista.
  const [selectedId, setSelectedId] = useState("");
  const [notice, setNotice] = useState("");
  const tabPad = useTabScrollBottomPadding();
  const handoff = estadoActividad(conv.estado);

  const openTicket = (id: string) => {
    setNotice("");
    setSelectedId(id);
  };

  const backToList = () => {
    setSelectedId("");
    refresh();
  };

  useEffect(() => {
    if (!focusSeq) return;
    const tid = (focusTicketId || "").trim();
    if (tid) {
      openTicket(tid);
      refresh();
    }
    onFocusConsumed?.();
    // Solo al llegar un focus nuevo (reclamo / push ticket).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional
  }, [focusSeq]);

  // Atrás de Android: del detalle vuelve a la lista (la pestaña solo está montada si está activa).
  useEffect(() => {
    if (!selectedId) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      backToList();
      return true;
    });
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- backToList solo usa setters estables
  }, [selectedId]);

  if (selectedId) {
    return (
      <TicketDetailScreen
        ticketId={selectedId}
        preview={items.find((i) => i.id === selectedId)}
        conv={conv}
        token={token}
        onBack={backToList}
        onNotFound={() => {
          setNotice("No encontramos este reclamo.");
          backToList();
        }}
        onGoEko={onGoEko}
        onAuthExpired={onExit}
      />
    );
  }

  return (
    <Screen safeBottom={false}>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setNotice("");
              refresh();
            }}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: tabPad },
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
            {notice ? <Banner>{notice}</Banner> : null}
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
            <TicketCard item={item} onPress={() => openTicket(item.id)} />
          </View>
        )}
      />
    </Screen>
  );
}

function makeStyles(t: Theme) {
  const { space, size } = t;
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
    item: { marginBottom: space.md },
  });
}
