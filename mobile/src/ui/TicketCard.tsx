import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { formatTicketWhen, labelTicketEstado, present } from "../present";
import { colors, spacing } from "../theme";
import type { PortalTicket } from "../types";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { Text } from "./Text";

export function TicketCard({
  item,
  selected,
  busy,
  onPress,
}: {
  item: PortalTicket;
  selected?: boolean;
  busy?: boolean;
  onPress: () => void;
}) {
  const title = present(item.categoria) || `Ticket ${item.id}`;
  const updated = formatTicketWhen(item.updated_at || item.created_at);
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
            <ActivityIndicator color={colors.brand} />
          ) : (
            <Badge label={labelTicketEstado(item.estado)} />
          )}
        </View>
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

const styles = StyleSheet.create({
  selected: { borderColor: colors.brand },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  title: { flex: 1, fontSize: 18 },
  meta: { marginTop: spacing.sm },
});
