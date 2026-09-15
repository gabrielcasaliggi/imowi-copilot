import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { ORG_SLUG, PRIVACY_URL } from "../config";
import { formatUserError } from "../errors";
import { peekDniHint, saveSession } from "../session";
import { colors, layout, radius, sizes, spacing } from "../theme";
import type { Branding } from "../theme";
import type { AuthPayload } from "../types";
import { Avatar } from "../ui/Avatar";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";
import { TextField } from "../ui/TextField";

type Mode = "dni" | "pin";
type Step = "auth" | "otp";

export function AuthScreen({
  branding,
  onAuthed,
}: {
  branding: Branding;
  onAuthed: (payload: AuthPayload) => void;
}) {
  const insets = useSafeAreaInsets();
  const topPad = Math.max(insets.top, 12) + 8;
  const bottomPad = Math.max(insets.bottom, 12) + 10;
  const [mode, setMode] = useState<Mode>("pin");
  const [step, setStep] = useState<Step>("auth");
  const [dni, setDni] = useState("");
  const [pin, setPin] = useState("");
  const [otp, setOtp] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [contactMasked, setContactMasked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void peekDniHint().then((hint) => {
      if (hint) setDni(hint);
    });
  }, []);

  const finish = async (payload: AuthPayload) => {
    await saveSession(payload, dni.trim());
    onAuthed(payload);
  };

  const onStartDni = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.authStart(dni.trim(), ORG_SLUG);
      setChallengeId(res.challenge_id);
      setContactMasked(res.contact_masked);
      if (res.debug_otp) setOtp(res.debug_otp);
      setStep("otp");
    } catch (err) {
      setError(formatUserError(err, "No se pudo enviar el código. Intentá nuevamente."));
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.authVerify(challengeId, otp.trim(), ORG_SLUG);
      await finish(res);
    } catch (err) {
      setError(formatUserError(err, "No pudimos verificar el código. Intentá nuevamente."));
    } finally {
      setBusy(false);
    }
  };

  const onPin = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.loginPin(dni.trim(), pin.trim(), ORG_SLUG);
      await finish(res);
    } catch (err) {
      setError(formatUserError(err, "No se pudo ingresar. Revisá DNI y PIN."));
    } finally {
      setBusy(false);
    }
  };

  const title =
    step === "otp"
      ? "Ingresá el código"
      : mode === "pin"
        ? "Ingresá con tu PIN"
        : "Primera vez";
  const subtitle =
    step === "otp"
      ? `Enviamos un código a ${contactMasked}`
      : mode === "pin"
        ? "Usá el DNI y el PIN de 6 a 8 dígitos."
        : "Te enviamos un código al email de la cooperativa.";

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: topPad, paddingBottom: bottomPad },
        ]}
      >
        <View style={styles.logoWrap}>
          <Avatar size="lg" />
        </View>
        <Text variant="kicker" style={styles.kicker}>
          {branding.orgHint}
        </Text>
        <Text variant="greeting" style={styles.title} numberOfLines={2}>
          {title}
        </Text>
        <Text variant="subtitle" style={styles.sub}>
          {subtitle}
        </Text>

        {step === "auth" && (
          <>
            <View style={styles.tabs} accessibilityRole="tablist">
              <Pressable
                onPress={() => {
                  setMode("pin");
                  setError("");
                }}
                style={[styles.tab, mode === "pin" && styles.tabOn]}
                accessibilityRole="tab"
                accessibilityState={{ selected: mode === "pin" }}
                accessibilityLabel="DNI y PIN"
              >
                <Text style={[styles.tabTxt, mode === "pin" && styles.tabTxtOn]}>DNI + PIN</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  setMode("dni");
                  setError("");
                }}
                style={[styles.tab, mode === "dni" && styles.tabOn]}
                accessibilityRole="tab"
                accessibilityState={{ selected: mode === "dni" }}
                accessibilityLabel="Primera vez"
              >
                <Text style={[styles.tabTxt, mode === "dni" && styles.tabTxtOn]}>Primera vez</Text>
              </Pressable>
            </View>
            <TextField
              label="DNI"
              value={dni}
              onChangeText={setDni}
              keyboardType="number-pad"
              placeholder="Solo números"
              editable={!busy}
              maxLength={11}
              autoComplete="off"
            />
            {mode === "pin" ? (
              <>
                <TextField
                  label="PIN"
                  value={pin}
                  onChangeText={setPin}
                  keyboardType="number-pad"
                  secureTextEntry
                  placeholder="6–8 dígitos"
                  editable={!busy}
                  maxLength={8}
                />
                <Button
                  label={busy ? "Ingresando…" : "Ingresar"}
                  onPress={() => void onPin()}
                  disabled={busy || !dni || pin.length < 6}
                  loading={busy}
                />
              </>
            ) : (
              <Button
                label={busy ? "Enviando código…" : "Enviar código"}
                onPress={() => void onStartDni()}
                disabled={busy || !dni}
                loading={busy}
              />
            )}
          </>
        )}

        {step === "otp" && (
          <>
            <TextField
              label="Código"
              value={otp}
              onChangeText={setOtp}
              keyboardType="number-pad"
              autoComplete="one-time-code"
              textContentType="oneTimeCode"
              placeholder="Ingresá el código"
              editable={!busy}
              maxLength={8}
            />
            <Button
              label={busy ? "Verificando…" : "Verificar"}
              onPress={() => void onVerify()}
              disabled={busy || otp.length < 4}
              loading={busy}
            />
            <Pressable
              onPress={() => {
                if (busy) return;
                setStep("auth");
                setError("");
              }}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Volver"
              style={styles.back}
            >
              <Text variant="kicker" style={styles.link}>Volver</Text>
            </Pressable>
          </>
        )}

        {error ? <Text variant="error" style={styles.err}>{error}</Text> : null}
        <Pressable
          onPress={() => void Linking.openURL(PRIVACY_URL)}
          hitSlop={8}
          accessibilityRole="link"
          accessibilityLabel="Política de privacidad"
          style={styles.back}
        >
          <Text variant="kicker" style={styles.link}>Política de privacidad</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  scroll: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
  },
  logoWrap: { alignSelf: "center", marginBottom: spacing.lg },
  kicker: { marginBottom: spacing.sm },
  title: { marginBottom: spacing.sm },
  sub: { marginBottom: spacing.xl },
  tabs: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg },
  tab: {
    flex: 1,
    minHeight: sizes.hit,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabOn: { backgroundColor: colors.brandMuted, borderColor: colors.brand },
  tabTxt: { color: colors.muted, fontSize: 13, fontWeight: "600" },
  tabTxtOn: { color: colors.brand },
  link: { textAlign: "center", marginTop: spacing.lg },
  back: { minHeight: sizes.hit, justifyContent: "center", marginTop: spacing.sm },
  err: { marginTop: spacing.lg },
});
