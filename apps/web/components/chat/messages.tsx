"use client";

import { CloudSun, LoaderCircle } from "lucide-react";
import { useEffect, useRef } from "react";

import type { ChatMessage } from "@mecha/api-client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

const TOOL_LABELS: Record<string, string> = {
  search_locations: "Looking up the location…",
  get_weather_forecast: "Fetching the forecast…",
  current_datetime: "Checking the clock…",
};

const SUGGESTIONS = [
  "What's the weather in Berlin right now?",
  "Will it rain in Podgorica this week?",
  "Compare today's weather in London and Tokyo.",
];

interface MessagesProps {
  messages: ChatMessage[];
  streaming: boolean;
  activeTool: string | null;
  error: string | null;
  onSuggestion: (content: string) => void;
}

export function Messages({ messages, streaming, activeTool, error, onSuggestion }: MessagesProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <CloudSun className="size-10 text-muted-foreground" aria-hidden />
        <div>
          <h1 className="text-lg font-semibold">What can mecha check for you?</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            An agent with live weather tools, streaming its answers.
          </p>
        </div>
        <div className="flex max-w-md flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <Button
              key={suggestion}
              variant="outline"
              size="sm"
              onClick={() => onSuggestion(suggestion)}
            >
              {suggestion}
            </Button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-6">
        {messages.map((message, index) => (
          <div
            key={index}
            className={cn(
              "text-sm leading-relaxed whitespace-pre-wrap",
              message.role === "user"
                ? "max-w-[85%] self-end rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-primary-foreground"
                : "self-start",
            )}
          >
            {message.content}
            {message.role === "assistant" &&
              streaming &&
              index === messages.length - 1 &&
              message.content === "" &&
              activeTool === null && (
                <LoaderCircle
                  className="size-4 animate-spin text-muted-foreground"
                  aria-label="Waiting for the agent"
                />
              )}
          </div>
        ))}

        {activeTool !== null && (
          <Badge variant="secondary" className="self-start">
            <LoaderCircle className="animate-spin" aria-hidden />
            {TOOL_LABELS[activeTool] ?? `Running ${activeTool}…`}
          </Badge>
        )}

        {error !== null && (
          <Badge variant="destructive" className="h-auto self-start py-1 whitespace-normal">
            {error}
          </Badge>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
