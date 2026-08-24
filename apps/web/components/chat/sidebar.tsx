"use client";

import type { Conversation } from "@mecha/api-client";
import { Bot, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onDelete: (id: string) => void;
}

export function Sidebar({ conversations, activeId, onSelect, onDelete }: SidebarProps) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground max-md:hidden">
      <div className="flex items-center gap-2 px-4 py-4">
        <Bot className="size-5" aria-hidden />
        <span className="text-sm font-semibold">mecha</span>
      </div>

      <div className="px-3">
        <Button variant="outline" className="w-full justify-start" onClick={() => onSelect(null)}>
          <Plus data-icon="inline-start" aria-hidden />
          New chat
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-3 py-3">
        <ul className="flex flex-col gap-0.5">
          {conversations.map((conversation) => (
            <li key={conversation.id} className="group relative">
              <button
                type="button"
                title={conversation.title}
                onClick={() => onSelect(conversation.id)}
                className={cn(
                  "w-full truncate rounded-lg px-3 py-2 pr-9 text-left text-sm transition-colors hover:bg-sidebar-accent",
                  conversation.id === activeId &&
                    "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
              >
                {conversation.title}
              </button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Delete conversation "${conversation.title}"`}
                className="absolute top-1/2 right-1.5 -translate-y-1/2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                onClick={() => onDelete(conversation.id)}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </ScrollArea>

      <p className="border-t px-4 py-3 text-xs text-muted-foreground">
        Weather data by{" "}
        <a
          className="underline underline-offset-2 hover:text-foreground"
          href="https://open-meteo.com/"
          target="_blank"
          rel="noreferrer"
        >
          Open-Meteo
        </a>
      </p>
    </aside>
  );
}
