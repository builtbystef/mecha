import { listConversations, listMessages } from "@mecha/api-client";
import { queryOptions } from "@tanstack/react-query";

/**
 * Shared queryOptions so query keys and types are defined in one place, for
 * both useQuery and the imperative queryClient calls.
 *
 * Message keys nest under the conversations key; invalidations that mean
 * "just the list" must pass `exact: true`.
 */
export const conversationsQuery = queryOptions({
  queryKey: ["conversations"],
  queryFn: async () => {
    const { data } = await listConversations();
    if (data === undefined) throw new Error("Failed to load conversations");
    return data;
  },
});

export function messagesQuery(conversationId: string | null) {
  return queryOptions({
    queryKey: [...conversationsQuery.queryKey, conversationId, "messages"],
    queryFn: async () => {
      if (conversationId === null) return [];
      const { data } = await listMessages({ path: { conversation_id: conversationId } });
      if (data === undefined) throw new Error("Failed to load messages");
      return data;
    },
  });
}
