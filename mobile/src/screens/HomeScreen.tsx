import { useEffect, useRef, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useConnectivity } from "../hooks/useConnectivity";
import { useCreateClaim } from "../hooks/useCreateClaim";
import { useOvLinks } from "../hooks/useOvLinks";
import { useServices } from "../hooks/useServices";
import { firstName, present } from "../present";
import { layout, spacing } from "../theme";
import type { InboxConversation } from "../types";
import { BalanceCard } from "../ui/BalanceCard";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { ConnectivityCard } from "../ui/ConnectivityCard";
import { CreateClaimForm } from "../ui/CreateClaimForm";
import { QuickAction } from "../ui/QuickAction";
import { Screen } from "../ui/Screen";
import { SectionHeader } from "../ui/SectionHeader";
import { ServiceCard } from "../ui/ServiceCard";
import { ServicesSection } from "../ui/ServicesSection";
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
  connectivityRefreshKey = 0,
}: {
  conv: InboxConversation;
  orgHint: string;
  token: string;
  onQuickAction: (texto: string | null) => void;
  onOpenActivity: (ticketId?: string) => void;
  onAuthExpired: () => void;
  /** Incrementa tras push de incidente → reconsultar Connectivity (verdad actual). */
  connectivityRefreshKey?: number;
}) {
  const abonado = conv.abonado;
  const nombre = firstName(abonado?.nombre);
  const ticketId = present(conv.ticket_id);
  const encuesta = Boolean(conv.contexto?.encuesta_pendiente);
  const espera = conv.estado === "espera_agente";
  const conAgente = conv.estado === "con_agente";

  const connectivity = useConnectivity({ token, onAuthExpired });
  const ov = useOvLinks({ token, onAuthExpired });
  const services = useServices({ token, onAuthExpired });
  const claim = useCreateClaim({ token, onAuthExpired });
  const [showClaim, setShowClaim] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const connectivityY = useRef(0);

  useEffect(() => {
    if (!connectivityRefreshKey) return;
    connectivity.refresh();
    // Solo cuando cambia la key del push (no en cada render de refresh).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intencional
  }, [connectivityRefreshKey]);

  const submitClaim = async (input: {
    motivo: string;
    descripcion: string;
  }) => {
    const res = await claim.create(input);
    if (!res?.ticket?.id) return;
    setShowClaim(false);
    onOpenActivity(res.ticket.id);
  };

  const onViewConnectivity = (serviceId: string) => {
    connectivity.selectService(serviceId);
    requestAnimationFrame(() => {
      const y = Math.max(0, connectivityY.current - 16);
      scrollRef.current?.scrollTo({ y, animated: true });
    });
  };

  const hasCatalog = services.items.length > 0;

  return (
    <Screen safeBottom={false}>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
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
            onPress={() => onOpenActivity()}
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

        {present(abonado?.deuda_monto) ? (
          <View style={styles.gap}>
            <BalanceCard
              monto={abonado?.deuda_monto}
              onAskEko={onQuickAction}
              ovLinks={ov.data}
              ovLoading={ov.loading}
              ovTransportError={ov.error}
            />
          </View>
        ) : null}

        {/* Plan solo si aún no hay catálogo; con lista evita repetir Internet. */}
        <View style={styles.gap}>
          <ServiceCard
            plan={hasCatalog ? undefined : abonado?.plan}
            estado={abonado?.estado}
          />
        </View>

        <View style={styles.gap}>
          <ServicesSection
            items={services.items}
            loading={services.loading}
            error={services.error}
            unavailable={services.unavailable}
            msisdn={abonado?.linea_msisdn}
            onRetry={services.refresh}
            onViewConnectivity={onViewConnectivity}
            onAskEko={onQuickAction}
          />
        </View>

        <View
          style={styles.gap}
          onLayout={(e) => {
            connectivityY.current = e.nativeEvent.layout.y;
          }}
        >
          <ConnectivityCard
            data={connectivity.data}
            loading={connectivity.loading}
            error={connectivity.error}
            onRetry={connectivity.refresh}
            onAskEko={onQuickAction}
            onSelectService={onViewConnectivity}
            onCreateClaim={showClaim ? undefined : () => setShowClaim(true)}
          />
        </View>

        {showClaim ? (
          <View style={styles.gap}>
            <CreateClaimForm
              busy={claim.busy}
              error={claim.error}
              onSubmit={(input) => {
                void submitClaim(input);
              }}
              onCancel={() => {
                if (claim.busy) return;
                setShowClaim(false);
                claim.clearError();
              }}
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
