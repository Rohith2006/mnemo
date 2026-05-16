import React from "react";
import { TextInput, View } from "react-native";
import { SendButton } from "../Button";
import { radius, space, type as typeScale, useTheme } from "../../theme";

export function ChatComposer({
  value,
  onChangeText,
  onSend,
  disabled,
  loading,
}: {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  const t = useTheme();
  return (
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
        value={value}
        onChangeText={onChangeText}
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
            if (!disabled) onSend();
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
      <SendButton onPress={onSend} disabled={disabled} loading={loading} />
    </View>
  );
}
