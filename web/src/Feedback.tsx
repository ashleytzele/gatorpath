import { useState } from "react";
import { message, sendFeedback } from "./api";
import { FloatingCard } from "./FloatingCard";
import { Button } from "./ui";

const WARNING = "Please don't type your name or ID. We keep only your message: no email, no details about you.";

/** A "Send feedback" link and the card it opens. The server keeps the text and nothing about who sent it. */
export function FeedbackLink() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [state, setState] = useState<"writing" | "sending" | "sent">("writing");
  const [error, setError] = useState("");
  const close = () => {
    setOpen(false);
    if (state === "sent") setText("");
    setState("writing");
    setError("");
  };
  const send = () => {
    setState("sending");
    setError("");
    sendFeedback(text).then(
      () => setState("sent"),
      (e) => {
        setError(message(e));
        setState("writing"); // the text stays, so it can be sent again
      },
    );
  };
  return (
    <>
      <button type="button" className="pl-link" onClick={() => setOpen(true)}>
        Send feedback
      </button>
      {open && (
        <FloatingCard label="Send feedback" onClose={close}>
          {state === "sent" ? (
            <div className="fb">
              <h3>Thanks, we read every message.</h3>
              <Button kind="secondary" onClick={close}>Close</Button>
            </div>
          ) : (
            <div className="fb">
              <h3>What could be better?</h3>
              <label htmlFor="fb-text">Your message</label>
              <textarea id="fb-text" value={text} maxLength={2000} rows={6} onChange={(e) => setText(e.target.value)} />
              <p className="fb-note">{WARNING}</p>
              {error && <p role="alert" className="fb-error">{error}</p>}
              <div className="fb-actions">
                <Button disabled={!text.trim() || state === "sending"} onClick={send}>
                  {state === "sending" ? "Sending…" : "Send"}
                </Button>
                <Button kind="ghost" onClick={close}>Cancel</Button>
              </div>
            </div>
          )}
        </FloatingCard>
      )}
    </>
  );
}
