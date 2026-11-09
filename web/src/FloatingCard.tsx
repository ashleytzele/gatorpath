import { useLayoutEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** A viewport dialog for row details and choices. */
export function FloatingCard({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const card = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    card.current?.showModal();
    card.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => {
      card.current?.close();
      back?.focus();
    };
  }, []);
  return createPortal(
    <dialog aria-label={label} className="floating-card" ref={card} onCancel={(e) => { e.preventDefault(); onClose(); }} onClick={(e) => {
      const { left, right, top, bottom } = e.currentTarget.getBoundingClientRect();
      if (e.target === e.currentTarget && (e.clientX < left || e.clientX > right || e.clientY < top || e.clientY > bottom)) onClose();
    }}>
      <button type="button" className="floating-close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      {children}
    </dialog>,
    document.body,
  );
}
