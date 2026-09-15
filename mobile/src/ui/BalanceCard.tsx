import { StyleSheet, View } from "react-native";

import { isZeroAmount, present } from "../present";
import { spacing } from "../theme";
import { Card } from "./Card";
import { Text } from "./Text";

export function BalanceCard({ monto }: { monto?: string | null }) {
  const raw = present(monto);
  if (!raw) return null;
  const alDia = isZeroAmount(raw);
  return (
    <Card>
      <Text variant="label">Estado de cuenta</Text>
      {alDia ? (
        <Text variant="title" style={styles.ok}>Al día</Text>
      ) : (
        <View>
          <Text variant="title" style={styles.amount} numberOfLines={2} adjustsFontSizeToFit>
            {raw}
          </Text>
          <Text variant="meta">Saldo pendiente</Text>
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  ok: { marginTop: spacing.sm },
  amount: { marginTop: spacing.sm, marginBottom: spacing.xs },
});
