import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { formatTicketWhen, labelTicketEstado, present } from "../present";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import type { PortalTicket } from "../types";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { Text } from "./Text";

export function TicketCard({
  item,
  selected,
  busy,
  lastMovement,
  onPress,
}: {
  item: PortalTicket;
  selected?: boolean;
  busy?: boolean;
  /** Título del último evento, solo si la API lo trajo (detalle). Nunca se completa a mano. */
  lastMovement?: string | null;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const title = present(item.categoria) || `Ticket ${item.id}`;
  const updated = formatTicketWhen(item.updated_at || item.created_at);
  const movement = present(lastMovement);
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel={`Ticket ${item.id}, ${labelTicketEstado(item.estado)}`}
    >
      <Card style={selected ? styles.selected : undefined}>
        <View style={styles.row}>
          <Text variant="title" style={styles.title} numberOfLines={2}>
            {title}
          </Text>
          {busy && selected ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <Badge label={labelTicketEstado(item.estado)} />
          )}
        </View>
        {movement ? (
          <Text style={styles.movement} numberOfLines={2}>
            {movement}
          </Text>
        ) : null}
        <Text variant="meta" style={styles.meta} selectable>
          {item.id}
        </Text>
        {updated ? (
          <Text variant="meta" style={styles.meta}>
            Actualizado {updated}
          </Text>
        ) : null}
      </Card>
    </Pressable>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, fontSize } = t;
  return StyleSheet.create({
    selected: { borderColor: colors.primary },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: space.md,
    },
    title: { flex: 1, fontSize: fontSize.xl },
    meta: { marginTop: space.sm },
    movement: { marginTop: space.xs, fontSize: fontSize.md, color: colors.ink },
  });
}
