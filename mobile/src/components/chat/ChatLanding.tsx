import React, { useState } from "react";
import { View } from "react-native";
import { useChat } from "../../api/hooks";
import { ApiError } from "../../api/client";
import { MnemoMark } from "../Logo";
import { Callout } from "../Surfaces";
import { Text } from "../Text";
import { space, useTheme } from "../../theme";
import { ChatComposer } from "./ChatComposer";
import { randomGreeting } from "./greeting";

export function ChatLanding({
  userName,
  tz,
  onStarted,
}: {
  userName: string;
  tz: string;
  onStarted: (conversationId: string) => void;
}) {
  const t = useTheme();
  const [greeting] = useState(() => randomGreeting(tz, userName));
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const chat = useChat();

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setError(null);
    chat.mutate(
      { message: text },
      {
        onSuccess: (res) => onStarted(res.conversation_id),
        onError: (e) => setError(e instanceof ApiError ? e.message : "That did not go through. Try again."),
      },
    );
  };

  return (
    <View style={{ flex: 1, justifyContent: "center", alignItems: "center", padding: space.xxl, gap: space.xl }}>
      <MnemoMark size={40} animated color={t.ink} />
      <Text variant="title" style={{ textAlign: "center" }}>
        {greeting}
      </Text>
      {!!error && (
        <View style={{ width: "100%", maxWidth: 480 }}>
          <Callout text={error} tone="critical" />
        </View>
      )}
      <View style={{ width: "100%", maxWidth: 480 }}>
        <ChatComposer value={input} onChangeText={setInput} onSend={send} disabled={!input.trim() || chat.isPending} loading={chat.isPending} />
      </View>
    </View>
  );
}
