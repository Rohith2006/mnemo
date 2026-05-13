import React, { useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, TextInput, useWindowDimensions, View } from "react-native";
import { useChat } from "../../src/api/hooks";
import { ApiError } from "../../src/api/client";
import { SendButton } from "../../src/components/Button";
import { MnemoMark } from "../../src/components/Logo";
import { contentPadding, LargeTitle, Screen, TopBar, useScrollHeader } from "../../src/components/Screen";
import { Callout } from "../../src/components/Surfaces";
import { Text } from "../../src/components/Text";
import { stripMarkdown } from "../../src/utils/text";
import { radius, space, type as typeScale, useTheme } from "../../src/theme";
import type { ChatMessage } from "../../src/api/types";

type Bubble = ChatMessage & { id: string };

export default function ChatScreen() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const pad = contentPadding(width);
  const { scrolled, scrollProps } = useScrollHeader();

  const chat = useChat();
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [{ id: `${Date.now()}-u`, role: "user", content: text }, ...prev]);
    setInput("");
    setError(null);

    chat.mutate(
      { message: text, history },
      {
        onSuccess: (res) =>
          setMessages((prev) => [
            { id: `${Date.now()}-a`, role: "assistant", content: stripMarkdown(res.reply) },
            ...prev,
          ]),
        onError: (e) =>
          setError(e instanceof ApiError ? e.message : "That did not go through. Try again."),
      },
    );
  };

  return (
    <Screen>
      <TopBar title="Chat" showTitle={scrolled || messages.length > 0} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          {...scrollProps}
          data={messages}
          keyExtractor={(m) => m.id}
          inverted={messages.length > 0}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            paddingHorizontal: pad,
            paddingTop: space.lg,
            paddingBottom: space.lg,
          }}
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
              // No bubble. A hairline rule marks it as mnemo speaking, the way a
              // quoted block reads in a document.
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
          ListEmptyComponent={
            // Top-aligned, so the large title sits where it does on every other screen.
            <View style={{ paddingTop: space.md }}>
              <LargeTitle title="Chat" subtitle="For thinking something through out loud." />
              <View style={{ gap: space.sm }}>
                <MnemoMark size={22} />
                <Text variant="callout" tone="faint" style={{ maxWidth: 320 }}>
                  Ask about anything you have logged. For quick entries, Capture is faster and gives you a
                  record instead of a reply.
                </Text>
              </View>
            </View>
          }
        />

        <View
          style={{
            paddingHorizontal: pad,
            paddingTop: space.md,
            paddingBottom: space.md,
            borderTopWidth: 1,
            borderTopColor: t.hairline,
            backgroundColor: t.canvas,
          }}
        >
          {!!error && <Callout text={error} tone="critical" />}
          <View
            style={{
              flexDirection: "row",
              alignItems: "flex-end",
              gap: space.sm,
              backgroundColor: t.surface,
              borderWidth: 1,
              borderColor: t.hairline,
              borderRadius: radius.xl,
              paddingLeft: space.lg,
              paddingRight: space.xs,
              paddingVertical: space.xs,
            }}
          >
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder="Ask mnemo"
              placeholderTextColor={t.inkFaint}
              multiline
              accessibilityLabel="Message"
              // Enter sends, Shift+Enter inserts a newline — calling preventDefault
              // here stops both the browser's own newline insertion and RNW's
              // internal onSubmitEditing/blur handling for this keystroke.
              onKeyPress={(e: any) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              style={[
                typeScale.body,
                { flex: 1, color: t.ink, maxHeight: 120, paddingVertical: space.sm },
                // The browser's default focus ring on a web <textarea> would
                // otherwise show alongside this component's own border — an
                // RNW-only style extension @types/react-native doesn't model.
                { outlineStyle: "none" } as object,
              ]}
            />
            <SendButton onPress={send} disabled={!input.trim()} loading={chat.isPending} />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
