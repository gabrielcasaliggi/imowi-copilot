import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api";
import { PRIVACY_URL } from "../config";
import { MessageText } from "../MessageText";
import { getToken } from "../session";
import { colors, type Branding } from "../theme";
import type { InboxConversation, InboxMessage } from "../types";

function estadoLabel(estado: string, botName: string): string {
  if (estado === "bot") return `${botName} en línea`;
  if (estado === "espera_agente") return "Espera agente";
  if (estado === "con_agente") return "Con agente";
  if (estado === "cerrado") return "Cerrada";
  return estado;
}

export function ChatScreen({
  branding,
  conv: initialConv,
  mensajes: initialMsgs,
  token,
  onNeedPin,
  onExit,
}: {
  branding: Branding;
  conv: InboxConversation;
  mensajes: InboxMessage[];
  token: string;
  onNeedPin: boolean;
  onExit: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [conv, setConv] = useState(initialConv);
  const [mensajes, setMensajes] = useState(initialMsgs);
  const [texto, setTexto] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pin, setPin] = useState("");
  const [showPin, setShowPin] = useState(onNeedPin);
  const listRef = useRef<FlatList<InboxMessage>>(null);

  const esperaAgente = conv.estado === "espera_agente";
  const conAgente = conv.estado === "con_agente";
  const encuestaPendiente = Boolean(conv.contexto?.encuesta_pendiente);
  const nombre = conv.abonado?.nombre?.split(" ")[0] || "";
  const topPad = Math.max(insets.top, 12) + 8;
  const bottomPad = Math.max(insets.bottom, 12) + 10;

  const refresh = useCallback(async () => {
    const t = token || (await getToken());
    if (!t || !conv.id) return;
    try {
      const data = await api.conversation(conv.id, t);
      setConv(data.conversacion);
      setMensajes(data.mensajes || []);
    } catch {
      /* sesión vencida la maneja el padre al fallar un send */
    }
  }, [conv.id, token]);

  useEffect(() => {
    if (!esperaAgente && !conAgente) return;
    const id = setInterval(() => {
      void refresh();
    }, 4000);
    return () => clearInterval(id);
  }, [esperaAgente, conAgente, refresh]);

  const send = async (value: string) => {
    const outgoing = value.trim();
    if (!outgoing || busy) return;
    setError("");
    setTexto("");
    setBusy(true);
    setMensajes((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        conversacion_id: conv.id,
        autor: "cliente",
        texto: outgoing,
        direccion: "in",
        created_at: new Date().toISOString(),
      },
    ]);
    try {
      const res = await api.send(outgoing, token);
      if (res.conversacion) setConv(res.conversacion);
      setMensajes(res.mensajes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al enviar");
      setTexto(outgoing);
      setMensajes((prev) => prev.filter((m) => !String(m.id).startsWith("local-")));
    } finally {
      setBusy(false);
    }
  };

  const onSetPin = async () => {
    setBusy(true);
    setError("");
    try {
      await api.setPin(pin.trim(), token);
      setShowPin(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el PIN");
    } finally {
      setBusy(false);
    }
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
              try {
                await api.deleteAccount(token);
                onExit();
              } catch (err) {
                setError(err instanceof Error ? err.message : "No se pudieron borrar los datos");
              }
            })();
          },
        },
      ],
    );
  };

  if (showPin) {
    return (
      <View style={[styles.wrap, { paddingTop: topPad, paddingBottom: bottomPad }]}>
        <Text style={styles.title}>Creá un PIN</Text>
        <Text style={styles.sub}>Para entrar de nuevo sin código al email. 6 a 8 dígitos.</Text>
        <TextInput
          value={pin}
          onChangeText={setPin}
          keyboardType="number-pad"
          secureTextEntry
          placeholder="6–8 dígitos"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <Pressable onPress={onSetPin} disabled={busy || pin.length < 6} style={styles.btn}>
          <Text style={styles.btnTxt}>Guardar PIN</Text>
        </Pressable>
        <Pressable onPress={() => setShowPin(false)}>
          <Text style={styles.link}>Omitir por ahora</Text>
        </Pressable>
        {error ? <Text style={styles.err}>{error}</Text> : null}
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={[styles.wrap, { paddingTop: topPad }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={Platform.OS === "ios" ? topPad : 0}
    >
      <View style={styles.header}>
        <View style={styles.headerIdentity}>
          <Image
            source={require("../../assets/icon.png")}
            style={styles.headerAvatar}
            accessibilityLabel="Eko"
          />
          <View>
            <Text style={styles.headerTitle}>{branding.botDisplayName}</Text>
            <Text style={styles.headerSub}>
              <Text style={{ color: colors.online }}>● </Text>
              {estadoLabel(conv.estado, branding.botDisplayName)}
              {nombre ? ` · ${nombre}` : ""}
            </Text>
          </View>
        </View>
        <View style={styles.headerActions}>
          <Pressable onPress={onExit} hitSlop={12}>
            <Text style={styles.headerLink}>Salir</Text>
          </Pressable>
          <Pressable onPress={() => void Linking.openURL(PRIVACY_URL)} hitSlop={8}>
            <Text style={styles.headerLink}>Privacidad</Text>
          </Pressable>
          <Pressable onPress={onDeleteAccount} hitSlop={8}>
            <Text style={styles.dangerLink}>Eliminar datos</Text>
          </Pressable>
        </View>
      </View>

      {esperaAgente ? (
        <Text style={styles.banner}>
          Te estamos conectando con un agente. Podés seguir escribiendo acá.
        </Text>
      ) : null}
      {conAgente ? (
        <Text style={[styles.banner, styles.bannerOk]}>
          Un agente se unió. Las respuestas aparecen en este chat.
        </Text>
      ) : null}

      <FlatList
        ref={listRef}
        data={mensajes}
        keyExtractor={(m) => m.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => {
          const mine = item.autor === "cliente" || item.direccion === "in";
          const isEko = !mine && item.autor !== "agente";
          return (
            <View style={[styles.msgRow, mine ? styles.msgRowMine : styles.msgRowTheirs]}>
              {isEko ? (
                <Image
                  source={require("../../assets/icon.png")}
                  style={styles.msgAvatar}
                  accessibilityLabel={branding.botDisplayName}
                />
              ) : null}
              <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
                {!mine ? (
                  <Text style={styles.author}>
                    {item.autor === "agente" ? "Agente" : branding.botDisplayName}
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
        }}
      />

      {encuestaPendiente ? (
        <View style={styles.stars}>
          {[1, 2, 3, 4, 5].map((n) => (
            <Pressable key={n} onPress={() => void send(String(n))} style={styles.starBtn}>
              <Text style={styles.star}>★</Text>
              <Text style={styles.starN}>{n}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {error ? <Text style={styles.err}>{error}</Text> : null}

      <View style={[styles.composer, { paddingBottom: bottomPad }]}>
        <TextInput
          value={texto}
          onChangeText={setTexto}
          placeholder={
            encuestaPendiente
              ? "O respondé del 1 al 5…"
              : busy
                ? "Eko está respondiendo…"
                : "Escribí tu consulta…"
          }
          placeholderTextColor={colors.muted}
          style={styles.composerInput}
          editable={!busy}
          onSubmitEditing={() => void send(texto)}
          returnKeyType="send"
        />
        <Pressable
          onPress={() => void send(texto)}
          disabled={busy || !texto.trim()}
          style={[styles.sendBtn, (!texto.trim() || busy) && styles.btnOff]}
        >
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnTxt}>Enviar</Text>}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: 16 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  headerIdentity: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1, minWidth: 0 },
  headerAvatar: { width: 36, height: 36, borderRadius: 18 },
  headerTitle: { color: colors.text, fontSize: 18, fontWeight: "700" },
  headerSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  headerActions: { alignItems: "flex-end", gap: 4 },
  headerLink: { color: colors.muted, fontSize: 13 },
  dangerLink: { color: colors.danger, fontSize: 12 },
  banner: {
    color: colors.amber,
    backgroundColor: "rgba(251,191,36,0.1)",
    borderColor: "rgba(251,191,36,0.25)",
    borderWidth: 1,
    borderRadius: 10,
    padding: 10,
    fontSize: 12,
    marginBottom: 8,
  },
  bannerOk: {
    color: colors.brand,
    backgroundColor: "rgba(34,152,166,0.12)",
    borderColor: "rgba(34,152,166,0.28)",
  },
  list: { paddingVertical: 8, paddingBottom: 16 },
  msgRow: { flexDirection: "row", alignItems: "flex-end", marginBottom: 8, maxWidth: "90%" },
  msgRowMine: { alignSelf: "flex-end" },
  msgRowTheirs: { alignSelf: "flex-start" },
  msgAvatar: { width: 28, height: 28, borderRadius: 14, marginRight: 8, marginBottom: 2 },
  bubble: { flexShrink: 1, borderRadius: 16, padding: 10 },
  mine: { backgroundColor: colors.userBubble },
  theirs: { backgroundColor: colors.botBubble },
  author: { color: colors.brandDark, fontSize: 10, fontWeight: "700", marginBottom: 4 },
  msg: { fontSize: 15, lineHeight: 21 },
  msgMine: { color: "#fff" },
  msgTheirs: { color: colors.botText },
  linkMine: { color: "#ECFEFF", textDecorationLine: "underline" },
  linkTheirs: { color: colors.brandDark, textDecorationLine: "underline", fontWeight: "700" },
  composer: { flexDirection: "row", alignItems: "center", gap: 8, paddingTop: 10 },
  composerInput: {
    flex: 1,
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
  },
  sendBtn: {
    backgroundColor: colors.brand,
    borderRadius: 14,
    paddingHorizontal: 14,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  btnOff: { opacity: 0.45 },
  btn: {
    backgroundColor: colors.brand,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  btnTxt: { color: "#fff", fontWeight: "700" },
  title: { color: colors.text, fontSize: 22, fontWeight: "700", marginBottom: 8 },
  sub: { color: colors.muted, marginBottom: 16 },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 14,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 12,
  },
  link: { color: colors.muted, textAlign: "center", marginTop: 12 },
  err: { color: colors.danger, marginTop: 8, fontSize: 12 },
  stars: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  starBtn: { alignItems: "center", flex: 1 },
  star: { color: colors.amber, fontSize: 22 },
  starN: { color: colors.muted, fontSize: 10 },
});
