import React, { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, View } from "react-native";
import { useChat, useConversationMessages } from "../../api/hooks";
import { ApiError } from "../../api/client";
import { Callout } from "../Surfaces";
import { Text } from "../Text";
import { stripMarkdown } from "../../utils/text";
import { radius, space, useTheme } from "../../theme";
import { ChatComposer } from "./ChatComposer";

type Bubble = { id: string; role: "user" | "assistant"; content: string };

export function ChatThread({ conversationId }: { conversationId: string }) {
  const t = useTheme();
  const messagesQuery = useConversationMessages(conversationId);
  const chat = useChat();
  const [pending, setPending] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPending([]);
    setInput("");
    setError(null);
  }, [conversationId]);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setPending((prev) => [...prev, { id: `${Date.now()}-u`, role: "user", content: text }]);
    setInput("");
    setError(null);
    chat.mutate(
      { message: text, conversationId },
      {
        onSuccess: (res) =>
          setPending((prev) => [
            ...prev,
            { id: `${Date.now()}-a`, role: "assistant", content: stripMarkdown(res.reply) },
          ]),
        onError: (e) => setError(e instanceof ApiError ? e.message : "That did not go through. Try again."),
      },
    );
  };

  const loaded: Bubble[] = (messagesQuery.data ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.role === "assistant" ? stripMarkdown(m.content) : m.content,
  }));
  const display = [...loaded, ...pending].slice().reverse(); // newest first, for the inverted list

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={90}>
      {messagesQuery.isLoading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={t.inkFaint} />
        </View>
      ) : (
        <FlatList
          data={display}
          keyExtractor={(m) => m.id}
          inverted
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingHorizontal: space.xl, paddingTop: space.lg, paddingBottom: space.lg }}
          renderItem={({ item }) =>
            item.role === "user" ? (
              <View
                style={{
                  alignSelf: "flex-end",
                  maxWidth: "84%",
                  backgroundColor: t.sunken,
                  borderRadius: radius.lg,
                  paddingVertical: space.md,
                  paddingHorizontal: space.lg,
                  marginBottom: space.lg,
                }}
              >
                <Text variant="body">{item.content}</Text>
              </View>
            ) : (
              <View
                style={{
                  borderLeftWidth: 2,
                  borderLeftColor: t.hairlineStrong,
                  paddingLeft: space.lg,
                  marginBottom: space.xxl,
                }}
              >
                <Text variant="body">{item.content}</Text>
              </View>
            )
          }
        />
      )}

      <View
        style={{
          paddingHorizontal: space.xl,
          paddingTop: space.md,
          paddingBottom: space.md,
          borderTopWidth: 1,
          borderTopColor: t.hairline,
          backgroundColor: t.canvas,
        }}
      >
        {!!error && <Callout text={error} tone="critical" />}
        <ChatComposer value={input} onChangeText={setInput} onSend={send} disabled={!input.trim() || chat.isPending} loading={chat.isPending} />
      </View>
    </KeyboardAvoidingView>
  );
}
