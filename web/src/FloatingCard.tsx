import { useEffect, useRef, type ReactNode } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** "More about this row": a card under the row (put it inside a position: relative row). Esc and × close it. */
export function FloatingCard({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const card = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    card.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      back?.focus();
    };
  }, []);
  return (
    <div role="dialog" aria-label={label} className="floating-card" ref={card}>
      <button type="button" className="floating-close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      {children}
    </div>
  );
}
