import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { api } from "./src/api";
import { formatUserError, isAuthExpired } from "./src/errors";
import { useSession } from "./src/hooks/useSession";
import { AppShell } from "./src/navigation/AppShell";
import {
  attachPushListeners,
  consumeInitialPushResponse,
  registerPush,
  unregisterPush,
  type PushOpenIntent,
} from "./src/push";
import { AuthScreen } from "./src/screens/AuthScreen";
import { colors, layout, spacing } from "./src/theme";
import type { AppTab } from "./src/types";
import { Button } from "./src/ui/Button";
import { PinSetup } from "./src/ui/PinSetup";
import { Screen } from "./src/ui/Screen";
import { Text } from "./src/ui/Text";

export default function App() {
  const {
    branding,
    booting,
    bootError,
    retryBoot,
    token,
    needPin,
    setNeedPin,
    conv,
    mensajes,
    onAuthed,
    onExit,
    applyConversation,
  } = useSession();
  const [tab, setTab] = useState<AppTab>("home");
  const [pendingChatText, setPendingChatText] = useState("");
  const [pinGate, setPinGate] = useState(false);
  const [pin, setPin] = useState("");
  const [pinBusy, setPinBusy] = useState(false);
  const [pinError, setPinError] = useState("");
  const [connectivityRefreshKey, setConnectivityRefreshKey] = useState(0);
  const [pushFocusTicketId, setPushFocusTicketId] = useState("");
  const [pushFocusSeq, setPushFocusSeq] = useState(0);
  const authedRef = useRef(false);
  const pendingIntentRef = useRef<PushOpenIntent | null>(null);

  const authed = Boolean(conv && token);
  authedRef.current = authed;

  const applyIntentNavigation = (intent: PushOpenIntent) => {
    setTab(intent.tab);
    if (intent.refreshConnectivity) {
      setConnectivityRefreshKey((k) => k + 1);
    }
    if (intent.tab === "activity") {
      const tid = (intent.ticket_id || "").trim();
      setPushFocusTicketId(tid);
      setPushFocusSeq((n) => n + 1);
    }
  };

  const applyPushIntent = (intent: PushOpenIntent) => {
    if (authedRef.current) {
      applyIntentNavigation(intent);
      return;
    }
    pendingIntentRef.current = intent;
  };

  useEffect(() => {
    return attachPushListeners(applyPushIntent, applyPushIntent);
  }, []);

  useEffect(() => {
    void consumeInitialPushResponse().then((intent) => {
      if (intent) applyPushIntent(intent);
    });
  }, []);

  useEffect(() => {
    if (!authed || !token) return;
    void registerPush(token);
    if (pendingIntentRef.current) {
      const intent = pendingIntentRef.current;
      pendingIntentRef.current = null;
      applyIntentNavigation(intent);
    }
  }, [authed, token]);

  const handleAuthed = (payload: Parameters<typeof onAuthed>[0]) => {
    onAuthed(payload);
    const intent = pendingIntentRef.current;
    pendingIntentRef.current = null;
    if (intent) {
      applyIntentNavigation(intent);
    } else {
      setTab("home");
    }
    setPendingChatText("");
    setPinGate(payload.has_pin === false);
    setPin("");
    setPinError("");
  };

  const handleExit = () => {
    const current = token;
    void (async () => {
      await unregisterPush(current);
      await onExit();
    })();
    setTab("home");
    setPendingChatText("");
    setPinGate(false);
    setPin("");
    setPinError("");
  };

  const onSaveGatePin = async () => {
    if (pinBusy) return;
    setPinBusy(true);
    setPinError("");
    try {
      await api.setPin(pin.trim(), token);
      setNeedPin(false);
      setPinGate(false);
      setPin("");
    } catch (err) {
      if (isAuthExpired(err)) {
        handleExit();
        return;
      }
      setPinError(formatUserError(err, "No se pudo guardar el PIN. Intentá nuevamente."));
    } finally {
      setPinBusy(false);
    }
  };

  return (
    <SafeAreaProvider>
      {booting ? (
        <View style={styles.boot}>
          <StatusBar barStyle="light-content" />
          <ActivityIndicator color={colors.brand} />
        </View>
      ) : (
        <View style={styles.root}>
          <StatusBar barStyle="light-content" />
          {!authed && bootError ? (
            <Screen>
              <View style={styles.bootFail}>
                <Text variant="heading">Sin conexión</Text>
                <Text variant="subtitle" style={styles.bootCopy}>{bootError}</Text>
                <Button label="Reintentar" onPress={() => void retryBoot()} />
                <Button variant="ghost" label="Ingresar de nuevo" onPress={handleExit} />
              </View>
            </Screen>
          ) : !authed ? (
            <AuthScreen branding={branding} onAuthed={handleAuthed} />
          ) : pinGate ? (
            <Screen>
              <View style={styles.pinGate}>
                <PinSetup
                  pin={pin}
                  onChangePin={setPin}
                  onSave={() => void onSaveGatePin()}
                  onSkip={() => setPinGate(false)}
                  busy={pinBusy}
                  error={pinError}
                />
              </View>
            </Screen>
          ) : (
            <AppShell
              branding={branding}
              conv={conv!}
              mensajes={mensajes}
              token={token}
              needPin={needPin}
              tab={tab}
              onTab={setTab}
              pendingChatText={pendingChatText}
              connectivityRefreshKey={connectivityRefreshKey}
              pushFocusTicketId={pushFocusTicketId}
              pushFocusSeq={pushFocusSeq}
              onPushFocusConsumed={() => {
                setPushFocusTicketId("");
              }}
              onQuickAction={(texto) => {
                setTab("eko");
                setPendingChatText(texto || "");
              }}
              onPendingConsumed={() => setPendingChatText("")}
              onChange={applyConversation}
              onPinSaved={() => setNeedPin(false)}
              onExit={handleExit}
            />
          )}
        </View>
      )}
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  boot: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" },
  bootFail: {
    flex: 1,
    justifyContent: "center",
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
    gap: spacing.md,
  },
  bootCopy: { marginBottom: spacing.md },
  pinGate: {
    flex: 1,
    justifyContent: "center",
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
  },
});
