"use client";

import { X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import { ToneIcon, type Tone } from "@/components/ui";

/* Short confirmations after an action ("Review resolved"). Announced to
   screen readers; dismissed automatically after 5 seconds. */

interface Toast {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback((text: string, tone: Tone = "good") => {
    const id = nextId++;
    setToasts((t) => [...t.slice(-2), { id, tone, text }]);
    setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <ToneIcon tone={t.tone} />
            <span>{t.text}</span>
            <button type="button" className="icon-button" aria-label="Dismiss" onClick={() => dismiss(t.id)} style={{ width: 28, height: 28 }}>
              <X size={16} strokeWidth={1.75} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (text: string, tone?: Tone) => void {
  return useContext(ToastContext);
}
