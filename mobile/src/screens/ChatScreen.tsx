import { useEffect, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useConversation } from "../hooks/useConversation";
import { colors, spacing } from "../theme";
import type { Branding } from "../theme";
import type { InboxConversation, InboxMessage } from "../types";
import { Banner } from "../ui/Banner";
import { ChatComposer } from "../ui/ChatComposer";
import { ChatHeader } from "../ui/ChatHeader";
import { CsatBar } from "../ui/CsatBar";
import { EmptyState } from "../ui/EmptyState";
import { MessageBubble } from "../ui/MessageBubble";
import { Text } from "../ui/Text";

export function ChatScreen({
  branding,
  conv,
  mensajes,
  token,
  onExit,
  onChange,
  initialText,
  onInitialTextConsumed,
}: {
  branding: Branding;
  conv: InboxConversation;
  mensajes: InboxMessage[];
  token: string;
  onExit: () => void;
  onChange: (conv: InboxConversation | null, mensajes?: InboxMessage[]) => void;
  initialText?: string;
  onInitialTextConsumed?: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [texto, setTexto] = useState("");
  const listRef = useRef<FlatList<InboxMessage>>(null);
  const consumedRef = useRef("");

  const { busy, error, send, esperaAgente, conAgente } = useConversation({
    token,
    conv,
    mensajes,
    onChange,
    onAuthExpired: onExit,
  });

  const encuestaPendiente = Boolean(conv.contexto?.encuesta_pendiente);
  const nombre = conv.abonado?.nombre?.split(" ")[0] || "";
  const topPad = Math.max(insets.top, 12) + 8;
  const bottomPad = spacing.md;

  useEffect(() => {
    const pending = (initialText || "").trim();
    if (!pending) {
      consumedRef.current = "";
      return;
    }
    if (consumedRef.current === pending || busy) return;
    consumedRef.current = pending;
    setTexto("");
    void (async () => {
      const ok = await send(pending);
      if (!ok) setTexto(pending);
      onInitialTextConsumed?.();
    })();
  }, [initialText, busy, send, onInitialTextConsumed]);

  return (
    <KeyboardAvoidingView
      style={[styles.wrap, { paddingTop: topPad }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={Platform.OS === "ios" ? topPad : 0}
    >
      <ChatHeader
        branding={branding}
        estado={conv.estado}
        nombre={nombre}
        onExit={onExit}
      />

      {esperaAgente ? (
        <Banner>Te estamos conectando con un agente. Podés seguir escribiendo acá.</Banner>
      ) : null}
      {conAgente ? (
        <Banner tone="ok">Un agente se unió. Las respuestas aparecen en este chat.</Banner>
      ) : null}

      <FlatList
        ref={listRef}
        data={mensajes}
        keyExtractor={(m) => m.id}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        contentContainerStyle={[styles.list, mensajes.length === 0 && styles.listEmpty]}
        ListEmptyComponent={
          <EmptyState
            title={`Conversá con ${branding.botDisplayName}`}
            description="Escribí tu consulta. Eko usa tu cuenta de Cooperativa Batán para ayudarte con el servicio."
          />
        }
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <MessageBubble item={item} botName={branding.botDisplayName} />
        )}
      />

      {encuestaPendiente ? (
        <CsatBar busy={busy} onPick={(n) => void send(String(n))} />
      ) : null}

      {error ? <Text variant="error" style={styles.err}>{error}</Text> : null}

      <ChatComposer
        value={texto}
        onChangeText={setTexto}
        onSend={() => {
          if (busy) return;
          const outgoing = texto;
          setTexto("");
          void (async () => {
            const ok = await send(outgoing);
            if (!ok) setTexto(outgoing);
          })();
        }}
        busy={busy}
        paddingBottom={bottomPad}
        placeholder={
          encuestaPendiente
            ? "O respondé del 1 al 5…"
            : busy
              ? "Eko está respondiendo…"
              : "Escribí tu consulta…"
        }
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: spacing.lg },
  list: { paddingVertical: spacing.sm, paddingBottom: spacing.lg },
  listEmpty: { flexGrow: 1, justifyContent: "center" },
  err: { marginTop: spacing.sm, fontSize: 12 },
});
