export const colors = {
  brand: "#2298A6",
  brandDark: "#1b7a86",
  brandMuted: "rgba(34,152,166,0.16)",
  bg: "#0B1220",
  card: "#111827",
  surface: "#0F172A",
  border: "#1f2937",
  text: "#F8FAFC",
  muted: "#94A3B8",
  userBubble: "#2298A6",
  botBubble: "#1A2333",
  botText: "#E2E8F0",
  danger: "#F87171",
  amber: "#FBBF24",
  online: "#22C55E",
  onBrand: "#FFFFFF",
  tabBar: "#0E1626",
  amberMuted: "rgba(251,191,36,0.1)",
  amberBorder: "rgba(251,191,36,0.25)",
  brandBorder: "rgba(34,152,166,0.28)",
};

export const layout = {
  maxContent: 480,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

export const radius = {
  sm: 10,
  md: 14,
  lg: 16,
  xl: 20,
  full: 999,
};

export const typography = {
  kicker: { fontSize: 12, fontWeight: "500" as const, letterSpacing: 0.2 },
  label: { fontSize: 12, fontWeight: "500" as const },
  meta: { fontSize: 12, lineHeight: 16, fontWeight: "400" as const },
  body: { fontSize: 15, lineHeight: 22, fontWeight: "400" as const },
  subtitle: { fontSize: 14, lineHeight: 20, fontWeight: "400" as const },
  section: { fontSize: 13, fontWeight: "600" as const, letterSpacing: 0.3 },
  greeting: { fontSize: 28, lineHeight: 34, fontWeight: "700" as const },
  title: { fontSize: 22, fontWeight: "700" as const },
  heading: { fontSize: 24, lineHeight: 30, fontWeight: "700" as const },
  button: { fontSize: 16, fontWeight: "700" as const },
};

export const sizes = {
  hit: 44,
  icon: 22,
  avatarSm: 28,
  avatarMd: 36,
  avatarLg: 88,
  tab: 52,
};

export const elevation = {
  none: { borderWidth: 0 },
  card: { borderWidth: 1, borderColor: colors.border },
};

export type Branding = {
  botDisplayName: string;
  botDisplayNameShort: string;
  orgHint: string;
  productDisplayName: string;
  assistantTagline: string;
  assistantIntro: string;
};

export const defaultBranding: Branding = {
  botDisplayName: "Eko",
  botDisplayNameShort: "EKO",
  orgHint: "Cooperativa Batán",
  productDisplayName: "Soporte Batán",
  assistantTagline: "Tu asistente virtual",
  assistantIntro: "Hola, soy Eko, tu asistente virtual de Soporte Batán.",
};
