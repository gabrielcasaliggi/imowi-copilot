export const colors = {
  brand: "#2298A6",
  brandDark: "#1b7a86",
  bg: "#0B1220",
  card: "#111827",
  border: "#1f2937",
  text: "#F8FAFC",
  muted: "#94A3B8",
  userBubble: "#2298A6",
  botBubble: "#F1F5F9",
  botText: "#1E293B",
  danger: "#F87171",
  amber: "#FBBF24",
  online: "#22C55E",
};

export type Branding = {
  botDisplayName: string;
  botDisplayNameShort: string;
  orgHint: string;
  productDisplayName: string;
};

export const defaultBranding: Branding = {
  botDisplayName: "Eko",
  botDisplayNameShort: "EKO",
  orgHint: "Cooperativa Batán",
  productDisplayName: "Soporte Batán",
};
