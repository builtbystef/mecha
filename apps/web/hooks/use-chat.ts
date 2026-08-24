"use client";

import {
  type Conversation,
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
} from "@mecha/api-client";
import { useCallback, useEffect, useState } from "react";

import { readSseStream } from "@/lib/sse";

export interface UiMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Chat state: conversations come from the generated typed client; sending a
 * message streams the agent's SSE events (see apps/api chat.py for the
 * vocabulary) into the last assistant message.
 */
export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshConversations = useCallback(async () => {
    const { data } = await listConversations();
    if (data) setConversations(data);
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const selectConversation = useCallback(async (id: string | null) => {
    setActiveId(id);
    setError(null);
    if (id === null) {
      setMessages([]);
      return;
    }
    const { data } = await listMessages({ path: { conversation_id: id } });
    setMessages(data ?? []);
  }, []);

  const removeConversation = useCallback(
    async (id: string) => {
      await deleteConversation({ path: { conversation_id: id } });
      if (id === activeId) {
        setActiveId(null);
        setMessages([]);
      }
      await refreshConversations();
    },
    [activeId, refreshConversations],
  );

  const send = useCallback(
    async (content: string) => {
      if (streaming) return;
      setError(null);

      let conversationId = activeId;
      if (conversationId === null) {
        const { data } = await createConversation({});
        if (!data) {
          setError("Could not create a conversation. Is the API running?");
          return;
        }
        conversationId = data.id;
        setActiveId(conversationId);
      }

      setMessages((prev) => [
        ...prev,
        { role: "user", content },
        { role: "assistant", content: "" },
      ]);
      setStreaming(true);

      const appendToReply = (delta: string) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (!last || last.role !== "assistant") return prev;
          return [...prev.slice(0, -1), { role: "assistant", content: last.content + delta }];
        });
      };

      try {
        const response = await fetch(`/api/conversations/${conversationId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        });
        if (!response.ok || !response.body) {
          throw new Error(`request failed (${response.status})`);
        }
        for await (const { event, data } of readSseStream(response.body)) {
          if (event === "text-delta") {
            setActiveTool(null);
            appendToReply((JSON.parse(data) as { delta: string }).delta);
          } else if (event === "tool-call") {
            setActiveTool((JSON.parse(data) as { tool: string }).tool);
          } else if (event === "tool-result") {
            setActiveTool(null);
          } else if (event === "error") {
            setError((JSON.parse(data) as { message: string }).message);
          }
        }
      } catch {
        setError("The agent request failed. Is the API running?");
      } finally {
        setStreaming(false);
        setActiveTool(null);
        // Drop the placeholder if the run failed before any text arrived.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          return last?.role === "assistant" && last.content === "" ? prev.slice(0, -1) : prev;
        });
        // The first message becomes the conversation title server-side.
        void refreshConversations();
      }
    },
    [activeId, streaming, refreshConversations],
  );

  return {
    conversations,
    activeId,
    messages,
    streaming,
    activeTool,
    error,
    send,
    selectConversation,
    removeConversation,
  };
}
