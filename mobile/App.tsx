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
  const authedRef = useRef(false);
  const pendingTabRef = useRef<AppTab | null>(null);

  const authed = Boolean(conv && token);
  authedRef.current = authed;

  const applyPushTab = (next: AppTab) => {
    if (authedRef.current) {
      setTab(next);
      return;
    }
    pendingTabRef.current = next;
  };

  useEffect(() => {
    return attachPushListeners(applyPushTab);
  }, []);

  useEffect(() => {
    void consumeInitialPushResponse().then((next) => {
      if (next) applyPushTab(next);
    });
  }, []);

  useEffect(() => {
    if (!authed || !token) return;
    void registerPush(token);
    if (pendingTabRef.current) {
      setTab(pendingTabRef.current);
      pendingTabRef.current = null;
    }
  }, [authed, token]);

  const handleAuthed = (payload: Parameters<typeof onAuthed>[0]) => {
    onAuthed(payload);
    setTab(pendingTabRef.current || "home");
    pendingTabRef.current = null;
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
