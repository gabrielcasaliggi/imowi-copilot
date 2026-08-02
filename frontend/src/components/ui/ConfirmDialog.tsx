"use client";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  busy = false,
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-slate-950/70"
      role="presentation"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={description ? "confirm-dialog-desc" : undefined}
        className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-1.5">
          <h2 id="confirm-dialog-title" className="text-base font-semibold text-slate-50">
            {title}
          </h2>
          {description && (
            <p id="confirm-dialog-desc" className="text-sm text-slate-400 leading-relaxed">
              {description}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="text-xs px-3 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800/60 disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`text-xs px-3.5 py-2 rounded-lg font-semibold disabled:opacity-50 transition-all duration-200 ease-in-out ${
              danger
                ? "border border-rose-500/40 text-rose-200 hover:bg-rose-500/15"
                : "bg-ecolan-brand text-white hover:bg-ecolan-brand-dark shadow-sm"
            }`}
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
