"use client";

import { type ChatMessage, createConversation, deleteConversation } from "@mecha/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { conversationsQuery, messagesQuery } from "@/lib/queries";
import { readSseStream } from "@/lib/sse";

/**
 * Chat state. TanStack Query holds the conversation list and message
 * history; sending a message streams the agent's SSE events (see apps/api
 * chat.py) into the same query cache, so fetched and streamed data render
 * through one path.
 */
export function useChat() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: conversations = [] } = useQuery(conversationsQuery);

  // Disabled while streaming: a background refetch would overwrite the
  // not-yet-persisted messages. The cached data keeps rendering meanwhile.
  const { data: messages = [] } = useQuery({
    ...messagesQuery(activeId),
    enabled: activeId !== null && !streaming,
  });

  const selectConversation = useCallback((id: string | null) => {
    setActiveId(id);
    setError(null);
  }, []);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteConversation({ path: { conversation_id: id } }),
    onSuccess: (_result, id) => {
      setActiveId((current) => (current === id ? null : current));
      queryClient.removeQueries({ queryKey: messagesQuery(id).queryKey });
      void queryClient.invalidateQueries({ queryKey: conversationsQuery.queryKey, exact: true });
    },
  });

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
        // Seed the cache so the messages query doesn't race the updates
        // below with a fetch.
        queryClient.setQueryData(messagesQuery(conversationId).queryKey, []);
        setActiveId(conversationId);
      }

      const { queryKey } = messagesQuery(conversationId);
      const append = (message: ChatMessage) => {
        queryClient.setQueryData(queryKey, (prev = []) => [...prev, message]);
      };
      const appendToReply = (delta: string) => {
        queryClient.setQueryData(queryKey, (prev = []) => {
          const last = prev[prev.length - 1];
          if (!last || last.role !== "assistant") return prev;
          return [
            ...prev.slice(0, -1),
            { role: "assistant" as const, content: last.content + delta },
          ];
        });
      };

      append({ role: "user", content });
      append({ role: "assistant", content: "" });
      setStreaming(true);

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
        queryClient.setQueryData(queryKey, (prev = []) => {
          const last = prev[prev.length - 1];
          return last?.role === "assistant" && last.content === "" ? prev.slice(0, -1) : prev;
        });
        // The first message becomes the conversation title server-side.
        void queryClient.invalidateQueries({ queryKey: conversationsQuery.queryKey, exact: true });
      }
    },
    [activeId, streaming, queryClient],
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
    removeConversation: deleteMutation.mutate,
  };
}
