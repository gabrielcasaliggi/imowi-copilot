import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { api } from "../api";
import { ORG_SLUG } from "../config";
import { saveSession } from "../session";
import { colors, type Branding } from "../theme";
import type { AuthPayload } from "../types";

type Mode = "dni" | "pin";
type Step = "auth" | "otp";

export function AuthScreen({
  branding,
  onAuthed,
}: {
  branding: Branding;
  onAuthed: (payload: AuthPayload, dni: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("pin");
  const [step, setStep] = useState<Step>("auth");
  const [dni, setDni] = useState("");
  const [pin, setPin] = useState("");
  const [otp, setOtp] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [contactMasked, setContactMasked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const finish = async (payload: AuthPayload) => {
    await saveSession(payload, dni.trim());
    onAuthed(payload, dni.trim());
  };

  const onStartDni = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.authStart(dni.trim(), ORG_SLUG);
      setChallengeId(res.challenge_id);
      setContactMasked(res.contact_masked);
      if (res.debug_otp) setOtp(res.debug_otp);
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar");
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.authVerify(challengeId, otp.trim(), ORG_SLUG);
      await finish(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código incorrecto");
    } finally {
      setBusy(false);
    }
  };

  const onPin = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.loginPin(dni.trim(), pin.trim(), ORG_SLUG);
      await finish(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo ingresar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.wrap}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={styles.kicker}>{branding.orgHint} · Ecolan + IMOWI</Text>
      <Text style={styles.title}>
        {step === "otp" ? "Código de verificación" : "Ingresá a " + branding.productDisplayName}
      </Text>
      <Text style={styles.sub}>
        {step === "otp"
          ? `Enviamos un código a ${contactMasked}`
          : "Misma cuenta que el portal. Eko ya ve tu padrón, facturas y servicios."}
      </Text>

      {step === "auth" && (
        <>
          <View style={styles.tabs}>
            <Pressable
              onPress={() => setMode("pin")}
              style={[styles.tab, mode === "pin" && styles.tabOn]}
            >
              <Text style={[styles.tabTxt, mode === "pin" && styles.tabTxtOn]}>DNI + PIN</Text>
            </Pressable>
            <Pressable
              onPress={() => setMode("dni")}
              style={[styles.tab, mode === "dni" && styles.tabOn]}
            >
              <Text style={[styles.tabTxt, mode === "dni" && styles.tabTxtOn]}>Primera vez</Text>
            </Pressable>
          </View>
          <Text style={styles.label}>DNI</Text>
          <TextInput
            value={dni}
            onChangeText={setDni}
            keyboardType="number-pad"
            placeholder="Solo números"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          {mode === "pin" ? (
            <>
              <Text style={styles.label}>PIN</Text>
              <TextInput
                value={pin}
                onChangeText={setPin}
                keyboardType="number-pad"
                secureTextEntry
                placeholder="6–8 dígitos"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
              <Pressable
                onPress={onPin}
                disabled={busy || !dni || pin.length < 6}
                style={[styles.btn, busy && styles.btnOff]}
              >
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.btnTxt}>Ingresar</Text>
                )}
              </Pressable>
            </>
          ) : (
            <Pressable
              onPress={onStartDni}
              disabled={busy || !dni}
              style={[styles.btn, busy && styles.btnOff]}
            >
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.btnTxt}>Enviar código</Text>
              )}
            </Pressable>
          )}
        </>
      )}

      {step === "otp" && (
        <>
          <Text style={styles.label}>Código OTP</Text>
          <TextInput
            value={otp}
            onChangeText={setOtp}
            keyboardType="number-pad"
            autoComplete="one-time-code"
            placeholder="Ingresá el código"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          <Pressable
            onPress={onVerify}
            disabled={busy || otp.length < 4}
            style={[styles.btn, busy && styles.btnOff]}
          >
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.btnTxt}>Verificar</Text>
            )}
          </Pressable>
          <Pressable onPress={() => setStep("auth")}>
            <Text style={styles.link}>Volver</Text>
          </Pressable>
        </>
      )}

      {error ? <Text style={styles.err}>{error}</Text> : null}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.bg, padding: 24, justifyContent: "center" },
  kicker: { color: colors.muted, fontSize: 12, marginBottom: 8 },
  title: { color: colors.text, fontSize: 24, fontWeight: "700", marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 20, marginBottom: 24 },
  tabs: { flexDirection: "row", gap: 8, marginBottom: 16 },
  tab: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabOn: { backgroundColor: "rgba(34,152,166,0.18)", borderColor: colors.brand },
  tabTxt: { color: colors.muted, fontSize: 13 },
  tabTxtOn: { color: colors.brand, fontWeight: "600" },
  label: { color: colors.muted, fontSize: 12, marginBottom: 6 },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 14,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    marginBottom: 14,
  },
  btn: {
    backgroundColor: colors.brand,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 4,
  },
  btnOff: { opacity: 0.5 },
  btnTxt: { color: "#fff", fontWeight: "700", fontSize: 16 },
  link: { color: colors.muted, textAlign: "center", marginTop: 16 },
  err: { color: colors.danger, marginTop: 16, fontSize: 13 },
});
