import { useState } from "react";
import { Alert, Linking, ScrollView, StyleSheet, View } from "react-native";

import { api } from "../api";
import { PRIVACY_URL } from "../config";
import { formatUserError, isAuthExpired } from "../errors";
import { formatMontoDisplay, labelEstadoAbonado, labelServicio, parseAmount, present } from "../present";
import { layout, spacing } from "../theme";
import type { InboxAbonado } from "../types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { PinSetup } from "../ui/PinSetup";
import { Screen } from "../ui/Screen";
import { SectionHeader } from "../ui/SectionHeader";
import { StatusRow } from "../ui/StatusRow";
import { Text } from "../ui/Text";

export function AccountScreen({
  token,
  abonado,
  needPin,
  onPinSaved,
  onExit,
  onQuickAction,
}: {
  token: string;
  abonado?: InboxAbonado | null;
  needPin: boolean;
  onPinSaved: () => void;
  onExit: () => void;
  onQuickAction: (texto: string | null) => void;
}) {
  const [showPin, setShowPin] = useState(needPin);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const fail = (err: unknown, fallback: string) => {
    if (isAuthExpired(err)) {
      onExit();
      return;
    }
    setError(formatUserError(err, fallback));
  };

  const onSetPin = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api.setPin(pin.trim(), token);
      setShowPin(false);
      setPin("");
      onPinSaved();
    } catch (err) {
      fail(err, "No se pudo guardar el PIN. Intentá nuevamente.");
    } finally {
      setBusy(false);
    }
  };

  const onLogout = () => {
    Alert.alert("Cerrar sesión", "Vas a salir de la app en este dispositivo.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Cerrar sesión", onPress: onExit },
    ]);
  };

  const onDeleteAccount = () => {
    Alert.alert(
      "Eliminar datos de la app",
      "Se borra el PIN y los datos de esta app. El padrón de la cooperativa no se modifica. ¿Continuamos?",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Eliminar",
          style: "destructive",
          onPress: () => {
            void (async () => {
              if (busy) return;
              setBusy(true);
              setError("");
              try {
                await api.deleteAccount(token);
                onExit();
              } catch (err) {
                fail(err, "No se pudieron borrar los datos. Intentá nuevamente.");
              } finally {
                setBusy(false);
              }
            })();
          },
        },
      ],
    );
  };

  const hasFicha = Boolean(
    present(abonado?.nombre) ||
      present(abonado?.dni) ||
      present(abonado?.telefono_e164) ||
      present(abonado?.client_number) ||
      present(abonado?.servicio) ||
      present(abonado?.plan) ||
      present(abonado?.estado) ||
      present(abonado?.deuda_monto),
  );
  const deudaRaw = present(abonado?.deuda_monto);
  const deudaN = parseAmount(deudaRaw);
  const deudaPendiente = deudaN !== null && deudaN > 0;
  const saldoLabel = !deudaRaw
    ? ""
    : deudaN === 0
      ? "Cuenta al día"
      : formatMontoDisplay(deudaRaw, { absolute: deudaN !== null && deudaN < 0 });

  return (
    <Screen safeBottom={false}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Text variant="heading">Cuenta</Text>
        <Text variant="subtitle" style={styles.lead}>
          Datos de esta sesión y opciones de la app.
        </Text>

        {hasFicha ? (
          <Card style={styles.card}>
            <StatusRow label="Nombre" value={abonado?.nombre} />
            <StatusRow label="DNI" value={abonado?.dni} />
            <StatusRow label="Teléfono" value={abonado?.telefono_e164} />
            <StatusRow label="N° de cliente" value={abonado?.client_number} />
            <StatusRow label="Servicio" value={labelServicio(abonado?.servicio)} />
            <StatusRow label="Plan" value={abonado?.plan} />
            <StatusRow label="Estado de la cuenta" value={labelEstadoAbonado(abonado?.estado)} />
            <StatusRow
              label={deudaN !== null && deudaN < 0 ? "Saldo a favor" : "Saldo"}
              value={saldoLabel}
            />
            {deudaPendiente ? (
              <Button
                label="Resolver con Eko"
                onPress={() => onQuickAction("Quiero consultar mi deuda y opciones de pago.")}
                accessibilityHint="Abre Eko para consultar deuda y opciones de pago"
              />
            ) : deudaRaw ? (
              <Button
                variant="ghost"
                label="Consultar con Eko"
                onPress={() => onQuickAction("¿Cuánto debo?")}
                accessibilityHint="Abre Eko para consultar el saldo"
              />
            ) : null}
          </Card>
        ) : null}

        <View style={styles.block}>
          <SectionHeader title="Acceso" />
          {showPin ? (
            <PinSetup
              pin={pin}
              onChangePin={setPin}
              onSave={() => void onSetPin()}
              onSkip={() => setShowPin(false)}
              skipLabel={needPin ? "Omitir por ahora" : "Cancelar"}
              title={needPin ? "Creá un PIN" : "Cambiá tu PIN"}
              busy={busy}
              error={error}
            />
          ) : (
            <Button
              variant="ghost"
              label={needPin ? "Configurar PIN" : "Cambiar PIN"}
              disabled={busy}
              onPress={() => {
                setError("");
                setShowPin(true);
              }}
            />
          )}
        </View>

        <View style={styles.block}>
          <SectionHeader title="Privacidad y sesión" />
          <Button
            variant="ghost"
            label="Política de privacidad"
            disabled={busy}
            onPress={() => void Linking.openURL(PRIVACY_URL)}
          />
          <Button
            variant="ghost"
            label="Cerrar sesión"
            disabled={busy}
            onPress={onLogout}
          />
        </View>

        <View style={styles.dangerBlock}>
          <SectionHeader title="Datos de esta app" />
          <Text variant="meta" style={styles.dangerHint}>
            Esta acción no se puede deshacer desde la app.
          </Text>
          <Button
            variant="danger"
            label="Eliminar datos de la app"
            disabled={busy}
            onPress={onDeleteAccount}
          />
        </View>
        {error && !showPin ? <Text variant="error" style={styles.err}>{error}</Text> : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: spacing.xl,
    width: "100%",
    maxWidth: layout.maxContent,
    alignSelf: "center",
  },
  lead: { marginBottom: spacing.xl, marginTop: spacing.sm },
  card: { marginBottom: spacing.xl },
  block: { marginBottom: spacing.lg, gap: spacing.sm },
  dangerBlock: { marginTop: spacing.md, marginBottom: spacing.lg, gap: spacing.sm },
  dangerHint: { marginBottom: spacing.xs },
  err: { marginTop: spacing.md },
});
