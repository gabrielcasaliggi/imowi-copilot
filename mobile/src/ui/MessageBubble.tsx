import { StyleSheet, View } from "react-native";

import { useThemedStyles, type Theme } from "../theme/ThemeProvider";
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
  const styles = useThemedStyles(makeStyles);
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

function makeStyles(t: Theme) {
  const { colors, space, radius, fontSize } = t;
  return StyleSheet.create({
    msgRow: {
      flexDirection: "row",
      alignItems: "flex-end",
      marginBottom: space.md,
      maxWidth: "88%",
    },
    msgRowMine: { alignSelf: "flex-end" },
    msgRowTheirs: { alignSelf: "flex-start" },
    bubbleAfterAvatar: { marginLeft: space.sm },
    bubble: { flexShrink: 1, paddingHorizontal: space.md, paddingVertical: space.md, maxWidth: "100%" },
    mine: {
      backgroundColor: colors.primary,
      borderTopLeftRadius: radius.card,
      borderTopRightRadius: radius.card,
      borderBottomLeftRadius: radius.card,
      borderBottomRightRadius: space.xs,
    },
    theirs: {
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderTopLeftRadius: space.xs,
      borderTopRightRadius: radius.card,
      borderBottomLeftRadius: radius.card,
      borderBottomRightRadius: radius.card,
    },
    author: { color: colors.primary, fontSize: fontSize.xs, fontWeight: "700", marginBottom: space.xs },
    msg: { fontSize: fontSize.base, lineHeight: 22, flexShrink: 1 },
    msgMine: { color: colors.onPrimary },
    msgTheirs: { color: colors.ink },
    linkMine: { color: colors.onPrimary, textDecorationLine: "underline" },
    linkTheirs: { color: colors.primary, textDecorationLine: "underline", fontWeight: "700" },
  });
}
