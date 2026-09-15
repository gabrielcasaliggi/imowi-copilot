import { StyleSheet, View } from "react-native";

import { present } from "../present";
import { spacing } from "../theme";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { Text } from "./Text";

export function ServiceCard({
  servicio,
  plan,
  estado,
}: {
  servicio?: string | null;
  plan?: string | null;
  estado?: string | null;
}) {
  const s = present(servicio);
  const p = present(plan);
  const e = present(estado);
  if (!s && !p && !e) return null;
  return (
    <Card>
      {s ? <Badge label={s} /> : null}
      {p ? (
        <View style={styles.block}>
          <Text variant="label">Plan</Text>
          <Text variant="title" style={styles.plan} numberOfLines={3}>{p}</Text>
        </View>
      ) : null}
      {e ? (
        <View style={styles.block}>
          <Text variant="label">Estado del servicio</Text>
          <Text numberOfLines={3}>{e}</Text>
          <Text variant="meta" style={styles.hint}>
            Dato administrativo de tu cuenta. No es un diagnóstico de conexión.
          </Text>
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  block: { marginTop: spacing.md, gap: spacing.xs },
  plan: { fontSize: 20 },
  hint: { marginTop: spacing.xs },
});
