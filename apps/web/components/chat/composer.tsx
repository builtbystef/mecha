"use client";

import { ArrowUp } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ComposerProps {
  disabled: boolean;
  onSend: (content: string) => void;
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [draft, setDraft] = useState("");

  return (
    <form
      className="mx-auto flex w-full max-w-2xl gap-2 px-4 pb-4"
      onSubmit={(event) => {
        event.preventDefault();
        const content = draft.trim();
        if (!content || disabled) return;
        setDraft("");
        onSend(content);
      }}
    >
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Ask about the weather anywhere…"
        aria-label="Message"
        maxLength={4000}
        autoFocus
      />
      <Button
        type="submit"
        size="icon"
        aria-label="Send message"
        disabled={disabled || draft.trim() === ""}
      >
        <ArrowUp aria-hidden />
      </Button>
    </form>
  );
}
