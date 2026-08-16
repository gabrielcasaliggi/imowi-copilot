import Constants from "expo-constants";

const extra = (Constants.expoConfig?.extra || {}) as {
  apiUrl?: string;
  orgSlug?: string;
};

export const API_BASE = (
  process.env.EXPO_PUBLIC_API_URL ||
  extra.apiUrl ||
  "https://ibot.ecolan.com"
).replace(/\/$/, "");

export const ORG_SLUG =
  process.env.EXPO_PUBLIC_ORG_SLUG || extra.orgSlug || "coop-batan";

export const CANAL_HEADER = { "X-Canal": "app" } as const;
