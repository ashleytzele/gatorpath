import { useEffect, useRef, useState } from "react";
import type { Left } from "./api";
import { leftText, type ChatLine, type Suggestion } from "./logic";
import { Icon, NAVIGATOR, calmScroll, plainText } from "./ui";

/** A chat reply's light markdown as React elements (nothing is injected as HTML): paragraphs, "- " and "1. " lists,
 * **bold** and links. */
function Rich({ text }: { text: string }) {
  const inline = (raw: string) =>
    plainText(raw).split(/(\*\*[^*]+\*\*|https?:\/\/[^\s)]*[^\s).,;:])/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
        <b key={i}>{part.slice(2, -2)}</b>
      ) : /^https?:\/\//.test(part) ? (
        <a key={i} href={part} target="_blank" rel="noreferrer">
          {part}
        </a>
      ) : (
        part
      ),
    );
  const blocks: { list?: "ul" | "ol"; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const item = raw.match(/^\s*(?:([-*•])|\d+[.)])\s+(.*)$/);
    const list = item ? (item[1] ? "ul" : "ol") : undefined;
    const last = blocks[blocks.length - 1];
    if (!raw.trim()) blocks.push({ lines: [] });
    else if (list && last?.list === list) last.lines.push(item![2]);
    else blocks.push({ list, lines: [item ? item[2] : raw.replace(/^#+\s*/, "")] });
  }
  return (
    <>
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) => {
          if (!b.list) return <p key={i}>{inline(b.lines.join(" "))}</p>;
          const List = b.list;
          return (
            <List key={i}>
              {b.lines.map((line, j) => (
                <li key={j}>{inline(line)}</li>
              ))}
            </List>
          );
        })}
    </>
  );
}

const STILL_WORKS = "Your plan, schedule and course lists still work without the chat.";

/** Why the input is off, or "" when it is on. */
function whyOff(left: Left | undefined, aiDown: boolean) {
  if (aiDown) return `The AI helper isn't connected here. ${STILL_WORKS}`;
  if (left && left.day <= 0) return `You can ask again tomorrow. ${STILL_WORKS}`;
  if (left && left.hour <= 0) return `You can ask again within the hour. ${STILL_WORKS}`;
  return "";
}

export function ChatPanel(props: {
  open: boolean; // on a phone: full screen
  lines: ChatLine[];
  suggestions: Suggestion[];
  onSuggest: (id: Suggestion["id"]) => void;
  onSend: (text: string) => void;
  onUndo: () => void;
  canUndo: boolean;
  onShow: (codes: string[]) => void;
  busy: string;
  left?: Left;
  aiDown: boolean;
  hide: () => void;
}) {
  const { lines, busy, left, aiDown } = props;
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const off = whyOff(left, aiDown);
  const lastOk = lines.map((l) => l.kind === "ok" || l.kind === "problem").lastIndexOf(true);
  useEffect(() => {
    calmScroll(end.current, "nearest");
  }, [lines, busy]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`; // grows with the text, then scrolls
  }, [text]);
  const submit = () => {
    const ask = text.trim();
    if (!ask || busy || off) return;
    setText("");
    props.onSend(ask);
  };
  const latest = lines[lines.length - 1];
  const free = leftText(left);
  return (
    <aside className={`chat-dock ${props.open ? "open" : ""}`} aria-label="Chat with GatorPath">
      <div className="chat-dock-head">
        <h2>
          <Icon name="route" size={18} /> GatorPath
        </h2>
        <button className="chat-close" onClick={props.hide} aria-label="Hide the chat">
          Hide
        </button>
      </div>
      <div className="chat-thread" role="log" aria-live="polite" aria-label="Conversation">
        {lines.map((l, i) =>
          l.kind === "me" ? (
            <div className="chat-bubble user" key={i}>
              {l.text}
            </div>
          ) : l.kind === "ai" ? (
            <div className="chat-ai" key={i}>
              <Rich text={l.text} />
            </div>
          ) : (
            <div className={`chat-change ${l.kind}`} key={i}>
              <Icon name={l.kind === "ok" ? "check" : "warning"} size={15} />
              <div>
                <p>{plainText(l.kind === "ok" ? `Plan updated · ${l.text}` : l.text)}</p>
                {(l.kind === "ok" || l.kind === "problem") && (
                  <span className="chat-change-actions">
                    {!!l.codes?.length && <button onClick={() => props.onShow(l.codes!)}>Show in plan</button>}
                    {i === lastOk && props.canUndo && !busy && <button onClick={props.onUndo}>Undo</button>}
                  </span>
                )}
              </div>
            </div>
          ),
        )}
        {busy && (
          <div className="chat-working" role="status">
            <span className="chat-spinner" aria-hidden="true" />
            <span>
              Checking against the Bulletin…
              {busy !== "Checking against the Bulletin…" && <small> {busy}</small>}
            </span>
          </div>
        )}
        {!busy && latest && latest.kind !== "me" && props.suggestions.length > 0 && (
          <div className="chat-suggestions">
            {props.suggestions.map((s) => (
              <button
                className="suggested"
                key={s.id}
                disabled={s.id === "choose" && !!off}
                onClick={() => props.onSuggest(s.id)}
              >
                {s.label} <Icon name="arrow" size={14} />
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="chat-input">
        <textarea
          ref={box}
          rows={1}
          value={text}
          maxLength={2000}
          disabled={!!off}
          aria-label="Your message"
          aria-describedby="chat-note"
          placeholder={off ? "The chat is off for now" : "Ask anything, or say what to change"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") e.stopPropagation(); // Esc closes the plan's cards; typing here must not
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="chat-send" aria-label="Send" disabled={!text.trim() || !!busy || !!off} onClick={submit}>
          <Icon name="arrow" size={16} />
        </button>
      </div>
      <p className="chat-note" id="chat-note">
        {off || (
          <>
            {free && <b>{free}. </b>}
            Every change is checked against the Bulletin. Your DPR and an advisor have the final word.{" "}
            <a href={NAVIGATOR} target="_blank" rel="noreferrer">
              Ask an advisor in Navigator
            </a>
            .
          </>
        )}
      </p>
    </aside>
  );
}
