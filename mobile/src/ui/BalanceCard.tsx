import { Linking, Pressable, StyleSheet, View } from "react-native";

import { payButtonVariant } from "../balanceView";
import { formatMontoDisplay, parseAmount, present } from "../present";
import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
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
  const styles = useThemedStyles(makeStyles);
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
  const payLink = links.find((l) => l.id === "pay");
  const secondaryLinks = links.filter((l) => l.id !== "pay");
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
            <Text variant="meta">Te identificás en la oficina virtual.</Text>
          )}
          {payLink ? (
            <Button
              label={payLink.label}
              variant={payButtonVariant(n)}
              onPress={() => openLink(payLink.url as string)}
              accessibilityHint={`Abre ${payLink.label} en Oficina Virtual`}
            />
          ) : null}
          {secondaryLinks.length > 0 ? (
            <View style={styles.secondaryRow}>
              {secondaryLinks.map((link) => (
                <Button
                  key={link.id}
                  label={link.label}
                  variant="ghost"
                  onPress={() => openLink(link.url as string)}
                  accessibilityHint={`Abre ${link.label} en Oficina Virtual`}
                  style={styles.secondaryBtn}
                />
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {showOvUnavailable || showTransportFallback ? (
        <Text variant="meta" style={styles.ovMeta}>
          No pudimos obtener el acceso ahora.
        </Text>
      ) : null}

      {onAskEko ? (
        <Pressable
          onPress={() => onAskEko(actionText)}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
          accessibilityHint="Abre Eko para consultar la cuenta"
          hitSlop={4}
          style={styles.ekoLink}
        >
          <Text style={styles.ekoLinkTxt}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </Card>
  );
}

function makeStyles(t: Theme) {
  const { colors, space, size, fontSize } = t;
  return StyleSheet.create({
    ok: { marginTop: space.sm, marginBottom: space.xs },
    amount: { marginTop: space.sm, marginBottom: space.xs },
    ovMeta: { marginTop: space.sm },
    ovActions: { marginTop: space.md, gap: space.sm },
    secondaryRow: { flexDirection: "row", gap: space.sm },
    secondaryBtn: { flex: 1 },
    ekoLink: { marginTop: space.sm, minHeight: size.hit, justifyContent: "center", alignSelf: "flex-start" },
    ekoLinkTxt: {
      color: colors.primary,
      fontSize: fontSize.base,
      fontWeight: "700",
      textDecorationLine: "underline",
    },
  });
}
