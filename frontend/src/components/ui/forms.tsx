"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

/** Clase compartida para inputs/selects/textareas del hub (Ecolan). */
export const inputCls =
  "w-full bg-slate-950/80 border border-slate-600/80 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent";

export const inputClsCompact =
  "w-full bg-slate-950/80 border border-slate-600/80 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-100 placeholder:text-slate-500 transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent";

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
type BtnSize = "sm" | "md";

const VARIANT: Record<BtnVariant, string> = {
  primary:
    "font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark border border-transparent shadow-sm disabled:opacity-40",
  secondary:
    "border border-slate-600/80 text-slate-200 hover:bg-slate-800/50 hover:border-slate-500 disabled:opacity-50",
  ghost:
    "border border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 disabled:opacity-50",
  danger:
    "border border-rose-500/40 text-rose-200 hover:bg-rose-500/15 disabled:opacity-50",
  success:
    "border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/12 disabled:opacity-50",
};

const SIZE: Record<BtnSize, string> = {
  sm: "text-[11px] px-2.5 py-1.5 rounded-lg",
  md: "text-sm px-3.5 py-2 rounded-xl",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  style,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: BtnSize;
}) {
  return (
    <button
      type="button"
      className={`${SIZE[size]} ${VARIANT[variant]} transition-all duration-200 ease-in-out ${className}`}
      style={style}
      {...props}
    />
  );
}

export function TextField({
  className = "",
  compact,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { compact?: boolean }) {
  return (
    <input
      className={`${compact ? inputClsCompact : inputCls} ${className}`}
      {...props}
    />
  );
}

export function TextAreaField({
  className = "",
  compact,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { compact?: boolean }) {
  return (
    <textarea
      className={`${compact ? inputClsCompact : inputCls} resize-y ${className}`}
      {...props}
    />
  );
}
