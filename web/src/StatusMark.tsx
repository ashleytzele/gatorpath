import type { Mark } from "./logic.ts";

const WORD: Record<Mark, string> = {
  complete: "Complete",
  progress: "In progress",
  incomplete: "Incomplete",
  exception: "Exception",
  warning: "Warning",
};
const GLYPH: Record<Mark, string> = { complete: "✓", progress: "◐", incomplete: "○", exception: "E", warning: "!" };

/** The five requirement marks. The glyph is for the eye; the word is for a screen reader. */
export function StatusMark({ mark }: { mark: Mark }) {
  return (
    <span className={`status-mark ${mark}`}>
      <span aria-hidden="true">{GLYPH[mark]}</span>
      <span className="sr-only">{WORD[mark]}</span>
    </span>
  );
}
