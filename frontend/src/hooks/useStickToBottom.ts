"use client";

import { useCallback, useEffect, useRef } from "react";

const NEAR_BOTTOM_PX = 120;

/**
 * Auto-scroll al final solo si el usuario ya está cerca del fondo
 * (evita que el polling tire el scroll hacia abajo al leer arriba).
 */
export function useStickToBottom(
  deps: unknown[],
  opts?: { behavior?: ScrollBehavior; threshold?: number },
) {
  const threadRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const threshold = opts?.threshold ?? NEAR_BOTTOM_PX;
  const behavior = opts?.behavior ?? "smooth";

  const onScroll = useCallback(() => {
    const el = threadRef.current;
    if (!el) return;
    stick.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, [threshold]);

  const forceStick = useCallback(() => {
    stick.current = true;
  }, []);

  useEffect(() => {
    if (!stick.current) return;
    bottomRef.current?.scrollIntoView({ behavior });
    // deps Intencionalmente externas (mensajes, typing, etc.)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { threadRef, bottomRef, onScroll, forceStick };
}
