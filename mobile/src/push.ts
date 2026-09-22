import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import { api } from "./api";
import {
  intentFromPushData,
  type PushOpenIntent,
} from "./pushIncidente";
import type { AppTab } from "./types";

export type {
  CanonicalTicketEvent,
  PushOpenIntent,
  TicketPushPayload,
} from "./pushIncidente";
export {
  intentFromPushData,
  parseIncidentePush,
  parseTicketPush,
} from "./pushIncidente";

const PUSH_TOKEN_KEY = "expo_push_token";
const CHANNEL_ID = "eko";

type NotificationsModule = typeof import("expo-notifications");

let notifications: NotificationsModule | null | undefined;
let handlerReady = false;
let registerInFlight: Promise<void> | null = null;
let lastPostedToken = "";
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retriedOnce = false;

/** Expo Go (SDK 53+) no soporta push remoto. Evitar cargar el módulo. */
export function pushSupported(): boolean {
  return Constants.appOwnership !== "expo";
}

async function getNotifications(): Promise<NotificationsModule | null> {
  if (!pushSupported()) return null;
  if (notifications !== undefined) return notifications;
  try {
    notifications = await import("expo-notifications");
    return notifications;
  } catch {
    notifications = null;
    return null;
  }
}

function easProjectId(): string {
  const extra = (Constants.expoConfig?.extra || {}) as { eas?: { projectId?: string } };
  return (
    Constants.easConfig?.projectId ||
    extra.eas?.projectId ||
    ""
  );
}

/** Compat: solo tab (CREATE/RESOLVE/updated → home; agente → eko). */
export function tabFromPushData(raw: unknown): AppTab {
  return intentFromPushData(raw).tab;
}

async function ensureHandler(N: NotificationsModule): Promise<void> {
  if (handlerReady) return;
  handlerReady = true;
  N.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}

async function ensureAndroidChannel(N: NotificationsModule): Promise<void> {
  if (Platform.OS !== "android") return;
  await N.setNotificationChannelAsync(CHANNEL_ID, {
    name: "Eko",
    importance: N.AndroidImportance.DEFAULT,
    sound: "default",
    vibrationPattern: [0, 250],
    lightColor: "#2298A6",
  });
}

async function storedPushToken(): Promise<string> {
  return (await SecureStore.getItemAsync(PUSH_TOKEN_KEY)) || "";
}

async function savePushToken(token: string): Promise<void> {
  lastPostedToken = token;
  await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
}

async function clearLocalPushToken(): Promise<void> {
  lastPostedToken = "";
  retriedOnce = false;
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY);
}

async function obtainExpoPushToken(N: NotificationsModule): Promise<string> {
  const existing = await N.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted" && existing.canAskAgain) {
    const asked = await N.requestPermissionsAsync();
    status = asked.status;
  }
  if (status !== "granted") return "";

  await ensureAndroidChannel(N);
  const projectId = easProjectId();
  const tokenRes = projectId
    ? await N.getExpoPushTokenAsync({ projectId })
    : await N.getExpoPushTokenAsync();
  return (tokenRes.data || "").trim();
}

async function postDevice(portalToken: string, expoPushToken: string): Promise<void> {
  if (!portalToken || !expoPushToken) return;
  if (expoPushToken === lastPostedToken) return;
  const name = (Constants.deviceName || "").trim().slice(0, 80);
  await api.registerDevice(portalToken, {
    expo_push_token: expoPushToken,
    platform: Platform.OS,
    device_name: name || undefined,
  });
  await savePushToken(expoPushToken);
}

function scheduleOneRetry(portalToken: string): void {
  if (retriedOnce || retryTimer) return;
  retriedOnce = true;
  retryTimer = setTimeout(() => {
    retryTimer = null;
    void registerPush(portalToken);
  }, 8000);
}

/**
 * Pide permiso (si aplica), obtiene el Expo Push Token y registra el dispositivo.
 * En Expo Go es no-op (push remoto removido en SDK 53+).
 * Nunca lanza: un fallo no debe bloquear login/Home/Eko.
 */
export async function registerPush(portalToken: string): Promise<void> {
  if (!portalToken || !pushSupported()) return;
  if (registerInFlight) return registerInFlight;
  registerInFlight = (async () => {
    try {
      const N = await getNotifications();
      if (!N) return;
      await ensureHandler(N);
      const expoPushToken = await obtainExpoPushToken(N);
      if (!expoPushToken) return;
      await postDevice(portalToken, expoPushToken);
    } catch {
      scheduleOneRetry(portalToken);
    } finally {
      registerInFlight = null;
    }
  })();
  return registerInFlight;
}

/** DELETE /portal/devices si hay token local. Falla silenciosa. */
export async function unregisterPush(portalToken: string): Promise<void> {
  const expoPushToken = lastPostedToken || (await storedPushToken());
  try {
    if (portalToken && expoPushToken) {
      await api.unregisterDevice(portalToken, {
        expo_push_token: expoPushToken,
        platform: Platform.OS,
      });
    }
  } catch {
    // Sin loops: el backend queda para el próximo login.
  } finally {
    await clearLocalPushToken();
  }
}

export function attachPushListeners(
  onOpen: (intent: PushOpenIntent) => void,
  onForegroundIncidente?: (intent: PushOpenIntent) => void,
): () => void {
  if (!pushSupported()) return () => {};

  let removeReceived: (() => void) | undefined;
  let removeResponse: (() => void) | undefined;
  let cancelled = false;

  void (async () => {
    const N = await getNotifications();
    if (!N || cancelled) return;
    await ensureHandler(N);
    const received = N.addNotificationReceivedListener((notification) => {
      // Foreground: banner del sistema. Si es incidente, refrescar Connectivity.
      const intent = intentFromPushData(notification.request.content.data);
      if (intent.refreshConnectivity) {
        onForegroundIncidente?.(intent);
      }
    });
    const response = N.addNotificationResponseReceivedListener((res) => {
      onOpen(intentFromPushData(res.notification.request.content.data));
    });
    removeReceived = () => received.remove();
    removeResponse = () => response.remove();
  })();

  return () => {
    cancelled = true;
    removeReceived?.();
    removeResponse?.();
  };
}

export async function consumeInitialPushResponse(): Promise<PushOpenIntent | null> {
  if (!pushSupported()) return null;
  try {
    const N = await getNotifications();
    if (!N) return null;
    const res = await N.getLastNotificationResponseAsync();
    if (!res) return null;
    try {
      await N.clearLastNotificationResponseAsync();
    } catch {
      /* SDK sin clear */
    }
    return intentFromPushData(res.notification.request.content.data);
  } catch {
    return null;
  }
}
