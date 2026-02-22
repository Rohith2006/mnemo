import React, { useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, Text, View } from "react-native";
import { useChat } from "../../src/api/hooks";
import { ApiError } from "../../src/api/client";
import { Banner, Field, PrimaryButton } from "../../src/components/Primitives";
import { useTheme, spacing, radius } from "../../src/theme";
import { stripMarkdown } from "../../src/utils/text";
import type { ChatMessage } from "../../src/api/types";

type Bubble = ChatMessage & { id: string };

export default function ChatScreen() {
  const t = useTheme();
  const chat = useChat();
  const [messages, setMessages] = useState<Bubble[]>([
    { id: "welcome", role: "assistant", content: "This is for when you want to actually talk something through — for quick logging, use the Capture tab instead." },
  ]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    const userMsg: Bubble = { id: `${Date.now()}-u`, role: "user", content: text };
    const history = messages.filter((m) => m.id !== "welcome").map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [userMsg, ...prev]);
    setInput("");
    setError(null);

    chat.mutate({ message: text, history }, {
      onSuccess: (res) => {
        setMessages((prev) => [{ id: `${Date.now()}-a`, role: "assistant", content: stripMarkdown(res.reply) }, ...prev]);
      },
      onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't send that — try again."),
    });
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <FlatList
        data={messages}
        keyExtractor={(m) => m.id}
        inverted
        contentContainerStyle={{ padding: spacing.lg }}
        renderItem={({ item }) => (
          <View style={{
            alignSelf: item.role === "user" ? "flex-end" : "flex-start",
            backgroundColor: item.role === "user" ? t.accentSoft : t.surface,
            borderWidth: item.role === "assistant" ? 1 : 0, borderColor: t.border,
            borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.sm, maxWidth: "82%",
          }}>
            <Text style={{ color: t.text, fontSize: 15, lineHeight: 20 }}>{item.content}</Text>
          </View>
        )}
      />
      <View style={{ padding: spacing.md, borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.surface }}>
        {error && <Banner text={error} tone="danger" />}
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
          <View style={{ flex: 1 }}>
            <Field label="" value={input} onChangeText={setInput} placeholder="Ask me anything…" multiline />
          </View>
          <View style={{ width: 90 }}>
            <PrimaryButton title="Send" onPress={send} loading={chat.isPending} disabled={!input.trim()} />
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
