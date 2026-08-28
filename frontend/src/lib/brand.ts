/**
 * Branding del asistente abonado (N1) y producto abonado.
 * Distinct from Copilot NOC (consola operadores / Operations Hub).
 */

export type Branding = {
  botDisplayName: string;
  botDisplayNameShort: string;
  orgHint: string;
  productDisplayName: string;
  assistantTagline: string;
  assistantIntro: string;
};

const DEFAULTS: Branding = {
  botDisplayName: process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME?.trim() || "Eko",
  botDisplayNameShort: (
    process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME_SHORT?.trim() ||
    process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME?.trim() ||
    "Eko"
  ).toUpperCase(),
  orgHint: "Cooperativa Batán",
  productDisplayName:
    process.env.NEXT_PUBLIC_PRODUCT_DISPLAY_NAME?.trim() || "Soporte Batán",
  assistantTagline:
    process.env.NEXT_PUBLIC_ASSISTANT_TAGLINE?.trim() || "Tu asistente virtual",
  assistantIntro: "Hola, soy Eko, tu asistente virtual de Soporte Batán.",
};

let cached: Branding = { ...DEFAULTS };

export function getBranding(): Branding {
  return cached;
}

/** Label de badge/filtro para estado canal `bot`. */
export function botEstadoLabel(): string {
  return `${cached.botDisplayName} (N1)`;
}

/** Subtítulo del portal: «Asistido por Eko · tu asistente virtual». */
export function portalAssistantLine(): string {
  const tag = cached.assistantTagline.trim();
  const mid =
    tag.length > 1 && tag[0] === tag[0].toUpperCase()
      ? tag[0].toLowerCase() + tag.slice(1)
      : tag;
  return `Asistido por ${cached.botDisplayName} · ${mid}`;
}

export function applyBranding(partial: {
  bot_display_name?: string;
  bot_display_name_short?: string;
  org_hint?: string;
  product_display_name?: string;
  assistant_tagline?: string;
  assistant_intro?: string;
}): Branding {
  cached = {
    botDisplayName: partial.bot_display_name?.trim() || cached.botDisplayName,
    botDisplayNameShort: (
      partial.bot_display_name_short?.trim() ||
      partial.bot_display_name?.trim() ||
      cached.botDisplayNameShort
    ).toUpperCase(),
    orgHint: partial.org_hint?.trim() || cached.orgHint,
    productDisplayName:
      partial.product_display_name?.trim() || cached.productDisplayName,
    assistantTagline:
      partial.assistant_tagline?.trim() || cached.assistantTagline,
    assistantIntro: partial.assistant_intro?.trim() || cached.assistantIntro,
  };
  return cached;
}

export async function hydrateBranding(apiBase?: string): Promise<Branding> {
  const base = (apiBase || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
    /\/$/,
    "",
  );
  try {
    const res = await fetch(`${base}/api/v1/public/branding`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return cached;
    const data = (await res.json()) as {
      bot_display_name?: string;
      bot_display_name_short?: string;
      org_hint?: string;
      product_display_name?: string;
      assistant_tagline?: string;
      assistant_intro?: string;
    };
    return applyBranding(data);
  } catch {
    return cached;
  }
}
