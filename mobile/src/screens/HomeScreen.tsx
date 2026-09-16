import { ScrollView, StyleSheet, View } from "react-native";

import { useConnectivity } from "../hooks/useConnectivity";
import { firstName, labelServicio, present } from "../present";
import { layout, spacing } from "../theme";
import type { InboxConversation } from "../types";
import { BalanceCard } from "../ui/BalanceCard";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { ConnectivityCard } from "../ui/ConnectivityCard";
import { QuickAction } from "../ui/QuickAction";
import { Screen } from "../ui/Screen";
import { SectionHeader } from "../ui/SectionHeader";
import { ServiceCard } from "../ui/ServiceCard";
import { Text } from "../ui/Text";

const ACTIONS: { id: string; label: string; text: string | null; hint: string }[] = [
  {
    id: "internet",
    label: "Mi Internet",
    text: "¿Cómo está mi Internet?",
    hint: "Consulta el estado con Eko",
  },
  {
    id: "problema",
    label: "Tengo un problema",
    text: "Tengo un problema con mi servicio.",
    hint: "Abre el chat con Eko",
  },
  {
    id: "saldo",
    label: "Consultar saldo",
    text: "¿Cuánto debo?",
    hint: "Consulta el saldo con Eko",
  },
  {
    id: "ov",
    label: "Oficina virtual",
    text: "Quiero entrar a la oficina virtual.",
    hint: "Eko te pasa el acceso a la oficina virtual",
  },
];

export function HomeScreen({
  conv,
  orgHint,
  token,
  onQuickAction,
  onOpenActivity,
  onAuthExpired,
}: {
  conv: InboxConversation;
  orgHint: string;
  token: string;
  onQuickAction: (texto: string | null) => void;
  onOpenActivity: () => void;
  onAuthExpired: () => void;
}) {
  const abonado = conv.abonado;
  const nombre = firstName(abonado?.nombre);
  const ticketId = present(conv.ticket_id);
  const encuesta = Boolean(conv.contexto?.encuesta_pendiente);
  const espera = conv.estado === "espera_agente";
  const conAgente = conv.estado === "con_agente";

  const connectivity = useConnectivity({ token, onAuthExpired });

  return (
    <Screen safeBottom={false}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text variant="kicker">{orgHint}</Text>
        <Text variant="greeting" style={styles.hello} numberOfLines={2}>
          {nombre ? `Hola, ${nombre}` : "Hola"}
        </Text>
        <Text variant="subtitle" style={styles.lead}>
          Tu servicio y tus gestiones, en un solo lugar.
        </Text>

        {espera ? (
          <Banner
            tone="warning"
            onPress={() => onQuickAction(null)}
            actionLabel="Continuar conversación con Eko"
          >
            Tenés una gestión en curso. Un agente todavía no tomó el chat.
          </Banner>
        ) : null}
        {conAgente ? (
          <Banner
            tone="ok"
            onPress={() => onQuickAction(null)}
            actionLabel="Ir al chat"
          >
            Un agente está en tu conversación.
          </Banner>
        ) : null}
        {ticketId ? (
          <Banner
            tone="ok"
            onPress={onOpenActivity}
            actionLabel="Ver en Actividad"
          >
            {`Hay una referencia de ticket en este chat: ${ticketId}.`}
          </Banner>
        ) : null}
        {encuesta ? (
          <Banner
            tone="ok"
            onPress={() => onQuickAction(null)}
            actionLabel="Calificar en el chat"
          >
            Podés calificar la atención desde la conversación con Eko.
          </Banner>
        ) : null}

        <ServiceCard
          servicio={labelServicio(abonado?.servicio)}
          plan={abonado?.plan}
          estado={abonado?.estado}
        />

        <View style={styles.gap}>
          <ConnectivityCard
            data={connectivity.data}
            loading={connectivity.loading}
            error={connectivity.error}
            onRetry={connectivity.refresh}
            onAskEko={onQuickAction}
            onSelectService={connectivity.selectService}
          />
        </View>

        {present(abonado?.deuda_monto) ? (
          <View style={styles.gap}>
            <BalanceCard
              monto={abonado?.deuda_monto}
              onAskEko={onQuickAction}
            />
          </View>
        ) : null}

        <View style={styles.block}>
          <SectionHeader title="¿Qué necesitás hacer?" />
          <View style={styles.actions}>
            {ACTIONS.map((a) => (
              <QuickAction
                key={a.id}
                label={a.label}
                accessibilityHint={a.hint}
                onPress={() => onQuickAction(a.text)}
              />
            ))}
          </View>
          <Button
            label="Hablar con Eko"
            onPress={() => onQuickAction(null)}
            accessibilityHint="Abre el chat con el asistente"
            style={styles.ekoCta}
          />
        </View>
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
  },
  hello: { marginTop: spacing.xs, marginBottom: spacing.sm },
  lead: { marginBottom: spacing.xl },
  gap: { marginTop: spacing.md },
  block: { marginTop: spacing.xl },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  ekoCta: { marginTop: spacing.xs },
});
