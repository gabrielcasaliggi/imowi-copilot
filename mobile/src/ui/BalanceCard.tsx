import { Linking, StyleSheet, View } from "react-native";

import { formatMontoDisplay, parseAmount, present } from "../present";
import { spacing } from "../theme";
import type { OvLinkItem, OvLinksResponse } from "../types";
import { Button } from "./Button";
import { Card } from "./Card";
import { Text } from "./Text";

function availableLinks(data: OvLinksResponse | null): OvLinkItem[] {
  if (!data) return [];
  if (data.status === "unavailable" || data.status === "unknown") return [];
  return (data.links || []).filter(
    (l) => l.available && typeof l.url === "string" && l.url.startsWith("http"),
  );
}

export function BalanceCard({
  monto,
  onAskEko,
  ovLinks,
  ovLoading,
  ovTransportError,
}: {
  monto?: string | null;
  onAskEko?: (texto: string) => void;
  ovLinks?: OvLinksResponse | null;
  ovLoading?: boolean;
  /** Error HTTP/red distinto de status=unavailable del contrato. */
  ovTransportError?: string;
}) {
  const raw = present(monto);
  if (!raw) return null;
  const n = parseAmount(raw);
  const alDia = n === 0;
  const aFavor = n !== null && n < 0;
  const display = formatMontoDisplay(raw, { absolute: aFavor });

  const actionLabel = alDia || aFavor ? "Consultar con Eko" : "Resolver con Eko";
  const actionText = alDia || aFavor
    ? "¿Cuánto debo?"
    : "Quiero consultar mi deuda y opciones de pago.";

  const links = availableLinks(ovLinks ?? null);
  const showOvUnavailable =
    !ovLoading &&
    !ovTransportError &&
    (ovLinks?.status === "unavailable" || ovLinks?.status === "unknown");
  const showTransportFallback = Boolean(ovTransportError) && !ovLoading;

  const openLink = (url: string) => {
    void Linking.openURL(url).catch(() => {});
  };

  return (
    <Card>
      <Text variant="label">Mi cuenta</Text>
      {alDia ? (
        <View>
          <Text variant="title" style={styles.ok}>Cuenta al día</Text>
          <Text variant="meta">No tenés saldo pendiente.</Text>
        </View>
      ) : aFavor ? (
        <View>
          <Text variant="title" style={styles.ok} numberOfLines={2} adjustsFontSizeToFit>
            {display}
          </Text>
          <Text variant="meta">Saldo a favor</Text>
        </View>
      ) : (
        <View>
          <Text variant="title" style={styles.amount} numberOfLines={2} adjustsFontSizeToFit>
            {display}
          </Text>
          <Text variant="meta">Saldo pendiente</Text>
        </View>
      )}

      {ovLoading ? (
        <Text variant="meta" style={styles.ovMeta}>
          Cargando accesos…
        </Text>
      ) : null}

      {!ovLoading && links.length > 0 ? (
        <View style={styles.ovActions}>
          {ovLinks?.authenticated === true ? null : (
            <Text variant="meta" style={styles.ovMeta}>
              Estos accesos abren la oficina virtual. Ahí vas a identificarte
              (DNI o usuario); no es una sesión ya abierta.
            </Text>
          )}
          {links.map((link) => (
            <Button
              key={link.id}
              label={link.label}
              variant={link.id === "pay" && !(alDia || aFavor) ? "primary" : "ghost"}
              onPress={() => openLink(link.url as string)}
              accessibilityHint={`Abre ${link.label} en Oficina Virtual`}
              style={styles.ovBtn}
            />
          ))}
        </View>
      ) : null}

      {showOvUnavailable || showTransportFallback ? (
        <Text variant="meta" style={styles.ovMeta}>
          No pudimos obtener el acceso ahora.
        </Text>
      ) : null}

      {onAskEko ? (
        <Button
          label={actionLabel}
          variant={
            links.length > 0 || alDia || aFavor
              ? "ghost"
              : "primary"
          }
          onPress={() => onAskEko(actionText)}
          accessibilityHint="Abre Eko para consultar la cuenta"
          style={styles.cta}
        />
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  ok: { marginTop: spacing.sm, marginBottom: spacing.xs },
  amount: { marginTop: spacing.sm, marginBottom: spacing.xs },
  cta: { marginTop: spacing.md },
  ovMeta: { marginTop: spacing.sm },
  ovActions: { marginTop: spacing.md, gap: spacing.sm },
  ovBtn: { marginTop: 0 },
});
