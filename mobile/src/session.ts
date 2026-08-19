import * as SecureStore from "expo-secure-store";

import type { AuthPayload } from "./types";

const TOKEN_KEY = "portal_token";
const CONV_KEY = "conv_id";
const DNI_KEY = "dni_hint";

async function safeGet(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function safeSet(key: string, value: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(key, value);
  } catch {
    /* sin almacenamiento seguro: la sesión vive en memoria */
  }
}

async function safeDel(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key);
  } catch {
    /* ignore */
  }
}

export async function saveSession(payload: AuthPayload, dni?: string): Promise<void> {
  await safeSet(TOKEN_KEY, payload.portal_token);
  await safeSet(CONV_KEY, payload.conversacion.id);
  if (dni) await safeSet(DNI_KEY, dni);
}

export async function loadSession(): Promise<{
  token: string;
  convId: string;
  dni: string;
} | null> {
  const token = await safeGet(TOKEN_KEY);
  const convId = await safeGet(CONV_KEY);
  const dni = (await safeGet(DNI_KEY)) || "";
  if (!token || !convId) return null;
  return { token, convId, dni };
}

export async function clearSession(): Promise<void> {
  await safeDel(TOKEN_KEY);
  await safeDel(CONV_KEY);
}

export async function getToken(): Promise<string> {
  return (await safeGet(TOKEN_KEY)) || "";
}
