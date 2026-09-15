import { StyleSheet, ScrollView, View } from "react-native";

import { present } from "../present";
import { layout, spacing } from "../theme";
import type { InboxConversation } from "../types";
import { Banner } from "../ui/Banner";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Screen } from "../ui/Screen";
import { Text } from "../ui/Text";

function estadoActividad(estado: string): string {
  if (estado === "espera_agente") return "Estás en espera de un agente.";
  if (estado === "con_agente") return "Un agente está en este chat.";
  if (estado === "cerrado") return "La conversación está cerrada.";
  return "";
}

export function ActivityScreen({ conv }: { conv: InboxConversation }) {
  const ticketId = present(conv.ticket_id);
  const handoff = estadoActividad(conv.estado);
  const hasActivity = Boolean(ticketId || handoff);

  return (
    <Screen safeBottom={false}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      <Text variant="heading" style={styles.title}>Actividad</Text>
      <Text variant="subtitle" style={styles.lead}>
        Solo lo que ya figura en esta conversación.
      </Text>

      {!hasActivity ? (
        <EmptyState
          title="Sin actividad todavía"
          description="Cuando Eko derive a un agente o quede un ticket asociado a este chat, lo vas a ver acá. No hay un historial aparte."
        />
      ) : (
        <View style={styles.stack}>
          {handoff ? (
            <Banner tone={conv.estado === "con_agente" ? "ok" : "warning"}>{handoff}</Banner>
          ) : null}
          {ticketId ? (
            <Card>
              <Text variant="label">Referencia de ticket</Text>
              <Text variant="title" style={styles.ticket} selectable numberOfLines={2}>{ticketId}</Text>
              <Text variant="meta" style={styles.note}>
                Identificador asociado a este chat. El detalle del ticket no está disponible en la app.
              </Text>
            </Card>
          ) : null}
        </View>
      )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xl,
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
    flexGrow: 1,
  },
  title: { marginBottom: spacing.sm },
  lead: { marginBottom: spacing.xl },
  stack: { gap: spacing.md },
  ticket: { marginTop: spacing.sm },
  note: { marginTop: spacing.sm },
});
