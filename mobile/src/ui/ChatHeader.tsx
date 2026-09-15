import { Pressable, StyleSheet, View } from "react-native";

import { colors, sizes, spacing } from "../theme";
import type { Branding } from "../theme";
import { Avatar } from "./Avatar";
import { Text } from "./Text";

function estadoLabel(estado: string, botName: string): string {
  if (estado === "bot") return `${botName} atiende este chat`;
  if (estado === "espera_agente") return "Espera de un agente";
  if (estado === "con_agente") return "Con un agente";
  if (estado === "cerrado") return "Conversación cerrada";
  return estado;
}

export function ChatHeader({
  branding,
  estado,
  onExit,
}: {
  branding: Branding;
  estado: string;
  nombre?: string;
  onExit: () => void;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.identity}>
        <Avatar size="md" accessibilityLabel={branding.botDisplayName} />
        <View style={styles.copy}>
          <Text style={styles.title} numberOfLines={1}>{branding.botDisplayName}</Text>
          <Text variant="meta" style={styles.sub} numberOfLines={1}>
            {estadoLabel(estado, branding.botDisplayName)}
          </Text>
        </View>
      </View>
      <Pressable
        onPress={onExit}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="Cerrar sesión"
        style={styles.exit}
      >
        <Text variant="kicker">Salir</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  identity: { flexDirection: "row", alignItems: "center", gap: spacing.md, flex: 1, minWidth: 0 },
  copy: { flex: 1, minWidth: 0 },
  title: { color: colors.text, fontSize: 18, fontWeight: "700" },
  sub: { marginTop: 2 },
  exit: { minHeight: sizes.hit, minWidth: sizes.hit, alignItems: "flex-end", justifyContent: "center" },
});
