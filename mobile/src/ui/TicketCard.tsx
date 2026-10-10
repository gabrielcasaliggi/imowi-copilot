import Ionicons from "@expo/vector-icons/Ionicons";
import { Pressable, StyleSheet, View } from "react-native";

import { formatTicketWhen } from "../present";
import { useTheme, useThemedStyles, type Theme } from "../theme/ThemeProvider";
import { lastMovementTitle, ticketStatusLabel, ticketTitle } from "../ticketView";
import type { PortalTicket } from "../types";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { Text } from "./Text";

/** Reclamo en la lista: título legible, estado, último movimiento y fecha. Abre el detalle. */
export function TicketCard({ item, onPress }: { item: PortalTicket; onPress: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const title = ticketTitle(item);
  const status = ticketStatusLabel(item.estado);
  const movement = lastMovementTitle(item);
  const updated = formatTicketWhen(item.updated_at || item.created_at);
  const a11y = [title, status, movement, updated ? `Actualizado ${updated}` : ""]
    .filter(Boolean)
    .join(". ");
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      accessibilityHint="Abre el seguimiento del reclamo"
    >
      {({ pressed }) => (
        <Card style={pressed ? styles.pressed : undefined}>
          <View style={styles.row}>
            <Text variant="title" style={styles.title} numberOfLines={2}>
              {title}
            </Text>
            <Badge label={status} />
          </View>
          {movement ? (
            <Text style={styles.movement} numberOfLines={2}>
              {movement}
            </Text>
          ) : null}
          <View style={styles.footer}>
            <View style={styles.footerText}>
              {updated ? <Text variant="meta">Actualizado {updated}</Text> : null}
              <Text variant="meta" selectable>
                {item.id}
              </Text>
            </View>
            <Ionicons
              name="chevron-forward"
              size={20}
              color={colors.muted}
              accessibilityElementsHidden
              importantForAccessibility="no"
            />
          </View>
        </Card>
      )}
    </Pressable>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, fontSize } = t;
  return StyleSheet.create({
    pressed: { borderColor: colors.primary },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: space.md,
    },
    title: { flex: 1, fontSize: fontSize.xl },
    movement: { marginTop: space.sm, fontSize: fontSize.md, color: colors.ink },
    footer: {
      flexDirection: "row",
      alignItems: "flex-end",
      justifyContent: "space-between",
      marginTop: space.sm,
      gap: space.md,
    },
    footerText: { flex: 1, gap: space.xs },
  });
}
