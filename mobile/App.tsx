import { useEffect, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, View } from "react-native";

import { api } from "./src/api";
import { registerPush } from "./src/push";
import { AuthScreen } from "./src/screens/AuthScreen";
import { ChatScreen } from "./src/screens/ChatScreen";
import { clearSession, loadSession } from "./src/session";
import { colors, defaultBranding, type Branding } from "./src/theme";
import type { AuthPayload, InboxConversation, InboxMessage } from "./src/types";

export default function App() {
  const [branding, setBranding] = useState<Branding>(defaultBranding);
  const [booting, setBooting] = useState(true);
  const [token, setToken] = useState("");
  const [needPin, setNeedPin] = useState(false);
  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);

  useEffect(() => {
    void api.branding().then(setBranding);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const stored = await loadSession();
        if (!stored) return;
        const data = await api.conversation(stored.convId, stored.token);
        setToken(stored.token);
        setConv(data.conversacion);
        setMensajes(data.mensajes || []);
        void registerPush(stored.token).catch(() => {});
      } catch {
        await clearSession();
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  const onAuthed = (payload: AuthPayload) => {
    setToken(payload.portal_token);
    setConv(payload.conversacion);
    setMensajes(payload.mensajes || []);
    setNeedPin(payload.has_pin === false);
    void registerPush(payload.portal_token).catch(() => {});
  };

  const onExit = async () => {
    await clearSession();
    setToken("");
    setConv(null);
    setMensajes([]);
    setNeedPin(false);
  };

  if (booting) {
    return (
      <View style={styles.boot}>
        <StatusBar barStyle="light-content" />
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" />
      {conv && token ? (
        <ChatScreen
          branding={branding}
          conv={conv}
          mensajes={mensajes}
          token={token}
          onNeedPin={needPin}
          onExit={() => void onExit()}
        />
      ) : (
        <AuthScreen branding={branding} onAuthed={onAuthed} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  boot: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" },
});
