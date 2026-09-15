import { StyleSheet, View } from "react-native";

import { colors, radius, spacing } from "../theme";
import type { InboxMessage } from "../types";
import { Avatar } from "./Avatar";
import { MessageText } from "./MessageText";
import { Text } from "./Text";

export function MessageBubble({
  item,
  botName,
}: {
  item: InboxMessage;
  botName: string;
}) {
  const mine = item.autor === "cliente" || item.direccion === "in";
  const isEko = !mine && item.autor !== "agente";
  return (
    <View style={[styles.msgRow, mine ? styles.msgRowMine : styles.msgRowTheirs]}>
      {isEko ? <Avatar size="sm" accessibilityLabel={botName} /> : null}
      <View
        style={[
          styles.bubble,
          mine ? styles.mine : styles.theirs,
          isEko && styles.bubbleAfterAvatar,
        ]}
      >
        {!mine ? (
          <Text style={styles.author}>
            {item.autor === "agente" ? "Agente" : botName}
          </Text>
        ) : null}
        <MessageText
          texto={item.texto}
          style={[styles.msg, mine ? styles.msgMine : styles.msgTheirs]}
          linkStyle={mine ? styles.linkMine : styles.linkTheirs}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  msgRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    marginBottom: spacing.md,
    maxWidth: "88%",
  },
  msgRowMine: { alignSelf: "flex-end" },
  msgRowTheirs: { alignSelf: "flex-start" },
  bubbleAfterAvatar: { marginLeft: spacing.sm },
  bubble: { flexShrink: 1, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2, maxWidth: "100%" },
  mine: {
    backgroundColor: colors.userBubble,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: spacing.xs,
  },
  theirs: {
    backgroundColor: colors.botBubble,
    borderWidth: 1,
    borderColor: colors.border,
    borderTopLeftRadius: spacing.xs,
    borderTopRightRadius: radius.lg,
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
  },
  author: { color: colors.brand, fontSize: 11, fontWeight: "700", marginBottom: 4 },
  msg: { fontSize: 15, lineHeight: 22, flexShrink: 1 },
  msgMine: { color: colors.onBrand },
  msgTheirs: { color: colors.botText },
  linkMine: { color: colors.onBrand, textDecorationLine: "underline" },
  linkTheirs: { color: colors.brand, textDecorationLine: "underline", fontWeight: "700" },
});
