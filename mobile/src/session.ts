import * as SecureStore from "expo-secure-store";

import type { AuthPayload } from "./types";

const TOKEN_KEY = "portal_token";
const CONV_KEY = "conv_id";
const DNI_KEY = "dni_hint";

export async function saveSession(payload: AuthPayload, dni?: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, payload.portal_token);
  await SecureStore.setItemAsync(CONV_KEY, payload.conversacion.id);
  if (dni) await SecureStore.setItemAsync(DNI_KEY, dni);
}

export async function loadSession(): Promise<{
  token: string;
  convId: string;
  dni: string;
} | null> {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  const convId = await SecureStore.getItemAsync(CONV_KEY);
  const dni = (await SecureStore.getItemAsync(DNI_KEY)) || "";
  if (!token || !convId) return null;
  return { token, convId, dni };
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(CONV_KEY);
}

export async function getToken(): Promise<string> {
  return (await SecureStore.getItemAsync(TOKEN_KEY)) || "";
}
