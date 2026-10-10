import Ionicons from "@expo/vector-icons/Ionicons";
import { useEffect } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";

import { useTicketDetail } from "../hooks/useTicketDetail";
import { useTabScrollBottomPadding } from "../navigation/tabBar";
import { formatTicketWhen, present } from "../present";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import {
  eventTitle,
  formatTicketMoment,
  ticketReference,
  ticketStatusLabel,
  ticketTitle,
  timelineEvents,
} from "../ticketView";
import type { InboxConversation, PortalTicket, PortalTicketEvent } from "../types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Screen } from "../ui/Screen";
import { Text } from "../ui/Text";

export function TicketDetailScreen({
  ticketId,
  preview,
  conv,
  token,
  onBack,
  onNotFound,
  onGoEko,
  onAuthExpired,
}: {
  ticketId: string;
  /** Datos de la lista para pintar el encabezado mientras carga el detalle. */
  preview?: PortalTicket;
  conv: InboxConversation;
  token: string;
  onBack: () => void;
  /** 404: el reclamo no existe o no es del abonado. */
  onNotFound: () => void;
  onGoEko: () => void;
  onAuthExpired: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const tabPad = useTabScrollBottomPadding();
  const { detail, loading, refreshing, error, notFound, refresh, retry } = useTicketDetail({
    ticketId,
    token,
    onAuthExpired,
  });

  useEffect(() => {
    if (notFound) onNotFound();
    // Solo al pasar a 404.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional
  }, [notFound]);

  const ticket = detail?.ticket ?? preview;
  const title = ticket ? ticketTitle(ticket) : ticketReference(ticketId);
  const created = formatTicketWhen(ticket?.created_at);
  const eventos = timelineEvents(detail?.eventos);
  const canOpenEko =
    Boolean(detail?.ticket.conversacion_id) && detail?.ticket.conversacion_id === conv.id;

  return (
    <Screen safeBottom={false}>
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: tabPad }]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        <Pressable
          onPress={onBack}
          accessibilityRole="button"
          accessibilityLabel="Volver a tus reclamos"
          hitSlop={8}
          style={styles.back}
        >
          <Ionicons name="chevron-back" size={22} color={colors.primary} />
          <Text style={styles.backTxt}>Reclamos</Text>
        </Pressable>

        <View style={styles.header} accessible accessibilityRole="header">
          <Text variant="heading">{title}</Text>
          {ticket ? <Badge label={ticketStatusLabel(ticket.estado)} /> : null}
          <Text variant="meta" selectable>
            {ticketReference(ticketId)}
          </Text>
          {created ? <Text variant="meta">Creado el {created}</Text> : null}
        </View>

        {loading && !detail ? (
          <View style={styles.loading}>
            <ActivityIndicator color={colors.primary} />
            <Text variant="meta">Cargando el seguimiento…</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.error}>
            <Text variant="error">{error}</Text>
            <Button
              label="Reintentar"
              variant="ghost"
              onPress={retry}
              accessibilityLabel="Reintentar cargar el reclamo"
            />
          </View>
        ) : null}

        {detail ? (
          <Card style={styles.card}>
            <Text variant="label">Seguimiento</Text>
            {eventos.length === 0 ? (
              <Text variant="subtitle">Todavía no hay novedades.</Text>
            ) : (
              <View accessibilityRole="list">
                {eventos.map((ev, i) => (
                  <TimelineItem
                    key={ev.id || String(i)}
                    ev={ev}
                    first={i === 0}
                    last={i === eventos.length - 1}
                  />
                ))}
              </View>
            )}
          </Card>
        ) : null}

        {canOpenEko ? (
          <Button
            label="Consultar con Eko"
            onPress={onGoEko}
            accessibilityHint="Abre la conversación de este reclamo"
            style={styles.eko}
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

function TimelineItem({
  ev,
  first,
  last,
}: {
  ev: PortalTicketEvent;
  first: boolean;
  last: boolean;
}) {
  const styles = useThemedStyles(makeStyles);
  const title = eventTitle(ev);
  const detalle = present(ev.detalle);
  const when = formatTicketMoment(ev.created_at);
  const a11y = [last ? `Último movimiento: ${title}` : title, detalle, when]
    .filter(Boolean)
    .join(". ");
  return (
    <View style={styles.item} accessible accessibilityLabel={a11y}>
      <View style={styles.rail}>
        <View style={[styles.segment, first && styles.segmentHidden]} />
        <View style={[styles.dot, last && styles.dotLast]} />
        <View style={[styles.segment, styles.segmentGrow, last && styles.segmentHidden]} />
      </View>
      <View style={[styles.body, last && styles.bodyLast]}>
        {last ? <Text variant="kicker" style={styles.lastKicker}>Último movimiento</Text> : null}
        <Text style={[styles.itemTitle, last && styles.itemTitleLast]}>{title}</Text>
        {detalle ? <Text style={styles.itemDetail}>{detalle}</Text> : null}
        {when ? <Text variant="meta">{when}</Text> : null}
      </View>
    </View>
  );
}

const DOT = 12;

function makeStyles(t: Theme) {
  const { colors, space, size, radius, fontSize } = t;
  return StyleSheet.create({
    scroll: {
      width: "100%",
      maxWidth: size.maxContent,
      alignSelf: "center",
      gap: space.lg,
    },
    back: {
      flexDirection: "row",
      alignItems: "center",
      alignSelf: "flex-start",
      minHeight: size.hit,
      paddingRight: space.md,
      gap: space.xs,
    },
    backTxt: { color: colors.primary, fontSize: fontSize.base, fontWeight: "600" },
    header: { gap: space.sm },
    loading: { flexDirection: "row", alignItems: "center", gap: space.sm },
    error: { gap: space.sm },
    card: { gap: space.md },
    item: { flexDirection: "row", gap: space.md },
    rail: { width: DOT, alignItems: "center" },
    segment: { width: 2, height: space.sm, backgroundColor: colors.border },
    segmentGrow: { flex: 1, minHeight: space.sm },
    segmentHidden: { opacity: 0 },
    dot: {
      width: DOT,
      height: DOT,
      borderRadius: radius.pill,
      borderWidth: 2,
      borderColor: colors.borderStrong,
      backgroundColor: colors.surface,
    },
    dotLast: { borderColor: colors.primary, backgroundColor: colors.primary },
    body: { flex: 1, gap: space.xs, paddingBottom: space.lg },
    bodyLast: { paddingBottom: 0 },
    lastKicker: { color: colors.primary },
    itemTitle: { color: colors.ink, fontSize: fontSize.base, fontWeight: "600" },
    itemTitleLast: { fontWeight: "700" },
    itemDetail: { color: colors.ink, fontSize: fontSize.md },
    eko: { marginTop: space.xs },
  });
}
