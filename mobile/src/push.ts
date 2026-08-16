import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";

import { api } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function registerPush(portalToken: string): Promise<void> {
  if (!Device.isDevice) return;
  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const req = await Notifications.requestPermissionsAsync();
    status = req.status;
  }
  if (status !== "granted") return;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("eko", {
      name: "Eko",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 180, 80, 180],
      lightColor: "#2298A6",
    });
  }

  try {
    const token = (await Notifications.getExpoPushTokenAsync()).data;
    await api.registerDevice(portalToken, {
      expo_push_token: token,
      platform: Platform.OS,
      device_name: Device.modelName || Platform.OS,
    });
  } catch {
    // Sin projectId EAS / emulador: la app sigue; el push se activa al firmar con EAS.
  }
}
