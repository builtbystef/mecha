"use client";

import { Composer } from "@/components/chat/composer";
import { Messages } from "@/components/chat/messages";
import { Sidebar } from "@/components/chat/sidebar";
import { useChat } from "@/hooks/use-chat";

export default function Home() {
  const {
    conversations,
    activeId,
    messages,
    streaming,
    activeTool,
    error,
    send,
    selectConversation,
    removeConversation,
  } = useChat();

  return (
    <div className="flex h-dvh bg-background text-foreground">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onDelete={removeConversation}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <Messages
          messages={messages}
          streaming={streaming}
          activeTool={activeTool}
          error={error}
          onSuggestion={(content) => void send(content)}
        />
        <Composer disabled={streaming} onSend={(content) => void send(content)} />
      </main>
    </div>
  );
}
