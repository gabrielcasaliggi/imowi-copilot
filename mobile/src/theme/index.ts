// Branding del tenant (nombre del asistente, cooperativa). Colores y escalas: tokens.ts (design/tokens.json).

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
