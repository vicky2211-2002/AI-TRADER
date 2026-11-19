import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Check, Loader2, X, AlertTriangle, CheckCircle2, Info } from "lucide-react";

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/35 backdrop-blur-[2px]" onClick={onClose} />
      <div
        className={`card relative z-10 w-full ${wide ? "max-w-4xl" : "max-w-lg"} max-h-[88vh] overflow-y-auto p-6 fade-in`}
      >
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h2 className="font-display text-xl">{title}</h2>
            {subtitle && <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{subtitle}</p>}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>{hint}</p>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  danger,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex items-start gap-3 w-full text-left py-1"
    >
      <span
        className="mt-0.5 relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors"
        style={{ background: checked ? (danger ? "var(--err)" : "var(--accent)") : "var(--panel-2)", border: "1px solid var(--border)" }}
      >
        <span
          className="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform"
          style={{ transform: checked ? "translateX(18px)" : "translateX(3px)" }}
        />
      </span>
      <span>
        <span className="block text-sm">{label}</span>
        {hint && <span className="block text-[11px] mt-0.5" style={{ color: "var(--muted)" }}>{hint}</span>}
      </span>
    </button>
  );
}

export function StatusDot({ status }: { status: string }) {
  const color =
    status === "running" || status === "ok" || status === "connected"
      ? "var(--ok)"
      : status === "error" || status === "failed"
        ? "var(--err)"
        : status === "warn"
          ? "var(--warn)"
          : "var(--muted)";
  return (
    <span
      className="inline-block h-2 w-2 rounded-full flex-shrink-0"
      style={{ background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 18%, transparent)` }}
    />
  );
}

export function Spinner({ size = 14 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin" />;
}

export function Empty({
  icon,
  title,
  body,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      <div
        className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl"
        style={{ background: "var(--panel)", color: "var(--muted)" }}
      >
        {icon}
      </div>
      <h3 className="font-display text-lg">{title}</h3>
      <p className="mt-1 max-w-sm text-sm" style={{ color: "var(--muted)" }}>{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function JsonBox({ value }: { value: unknown }) {
  return (
    <pre
      className="text-[11px] leading-relaxed overflow-x-auto rounded-lg p-3"
      style={{ background: "var(--code)", border: "1px solid var(--border)" }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function RiskBadge({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-start gap-2 py-1">
      {ok ? (
        <CheckCircle2 size={14} style={{ color: "var(--ok)", marginTop: 2 }} />
      ) : (
        <AlertTriangle size={14} style={{ color: "var(--err)", marginTop: 2 }} />
      )}
      <div className="text-xs">
        <span className="font-medium">{label}</span>
        {detail && <span style={{ color: "var(--muted)" }}> — {detail}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------------
type ToastKind = "ok" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const ToastContext = createContext<{ push: (message: string, kind?: ToastKind) => void }>({
  push: () => {},
});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, kind: ToastKind = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4800);
  }, []);
  const value = useMemo(() => ({ push }), [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-5 right-5 z-[60] flex w-[340px] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="card flex items-start gap-2.5 px-3.5 py-3 text-sm fade-in"
            style={{ borderLeft: `3px solid ${t.kind === "error" ? "var(--err)" : t.kind === "info" ? "var(--warn)" : "var(--ok)"}` }}
          >
            <span className="mt-0.5">
              {t.kind === "error" ? (
                <AlertTriangle size={15} style={{ color: "var(--err)" }} />
              ) : t.kind === "info" ? (
                <Info size={15} style={{ color: "var(--warn)" }} />
              ) : (
                <Check size={15} style={{ color: "var(--ok)" }} />
              )}
            </span>
            <span className="flex-1 leading-snug">{t.message}</span>
            <button onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))} style={{ color: "var(--muted)" }}>
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
