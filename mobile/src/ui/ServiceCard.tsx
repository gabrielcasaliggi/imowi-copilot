import { StyleSheet, View } from "react-native";

import { labelEstadoAbonado, present } from "../present";
import { space } from "../theme/tokens";
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
  const e = labelEstadoAbonado(estado);
  if (!s && !p && !e) return null;
  return (
    <Card>
      {s ? <Badge label={s} /> : null}
      {p ? (
        <View style={styles.block}>
          <Text variant="label">Plan</Text>
          <Text variant="title" numberOfLines={3}>{p}</Text>
        </View>
      ) : null}
      {e ? (
        <View style={styles.block}>
          <Text variant="label">Estado de la cuenta</Text>
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
  block: { marginTop: space.md, gap: space.xs },
  hint: { marginTop: space.xs },
});
