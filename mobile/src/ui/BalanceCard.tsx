import { StyleSheet, View } from "react-native";

import { formatMontoDisplay, parseAmount, present } from "../present";
import { spacing } from "../theme";
import { Button } from "./Button";
import { Card } from "./Card";
import { Text } from "./Text";

export function BalanceCard({
  monto,
  onAskEko,
}: {
  monto?: string | null;
  onAskEko?: (texto: string) => void;
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
      {onAskEko ? (
        <Button
          label={actionLabel}
          variant={alDia || aFavor ? "ghost" : "primary"}
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
});
