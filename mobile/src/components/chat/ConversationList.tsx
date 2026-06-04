import React, { useState } from "react";
import { Alert, Platform, Pressable, TextInput, View } from "react-native";
import { useDeleteConversation, useRenameConversation } from "../../api/hooks";
import type { ConversationOut } from "../../api/types";
import { IconButton } from "../Button";
import { EmptyRow, Group, Row } from "../List";
import { Text } from "../Text";
import { radius, space, type as typeScale, useTheme } from "../../theme";

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffMs = Date.now() - then;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNewChat,
}: {
  conversations: ConversationOut[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}) {
  const t = useTheme();
  const rename = useRenameConversation();
  const del = useDeleteConversation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const startEditing = (c: ConversationOut) => {
    setEditingId(c.id);
    setDraftTitle(c.title);
  };

  const commitEditing = () => {
    const title = draftTitle.trim();
    if (editingId && title) rename.mutate({ id: editingId, title });
    setEditingId(null);
  };

  const confirmDelete = (id: string) => {
    const message = "This chat and everything in it will be permanently deleted.";
    if (Platform.OS === "web") {
      if (window.confirm(`Delete this chat?\n\n${message}`)) del.mutate(id);
      return;
    }
    Alert.alert("Delete this chat?", message, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => del.mutate(id) },
    ]);
  };

  return (
    <View style={{ flex: 1, padding: space.md }}>
      <Pressable
        onPress={onNewChat}
        accessibilityRole="button"
        accessibilityLabel="New chat"
        style={({ pressed }) => ({
          flexDirection: "row",
          alignItems: "center",
          gap: space.sm,
          padding: space.md,
          borderRadius: radius.md,
          backgroundColor: pressed ? t.sunken : "transparent",
          marginBottom: space.md,
        })}
      >
        <IconButton name="newChat" label="New chat" onPress={onNewChat} tone="ink" />
        <Text variant="bodyMedium">New chat</Text>
      </Pressable>

      {conversations.length === 0 ? (
        <EmptyRow>No chats yet. Send a message to start one.</EmptyRow>
      ) : (
        <Group>
          {conversations.map((c, i) => (
            <View key={c.id} style={{ backgroundColor: c.id === activeId ? t.sunken : "transparent" }}>
              {editingId === c.id ? (
                <View
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: space.sm,
                    paddingVertical: space.md,
                    paddingHorizontal: space.lg,
                    borderTopWidth: i === 0 ? 0 : 1,
                    borderTopColor: t.hairline,
                  }}
                >
                  <TextInput
                    value={draftTitle}
                    onChangeText={setDraftTitle}
                    autoFocus
                    onSubmitEditing={commitEditing}
                    onBlur={commitEditing}
                    style={[typeScale.body, { flex: 1, color: t.ink }, { outlineStyle: "none" } as object]}
                  />
                  <IconButton name="check" label="Save title" onPress={commitEditing} tone="ink" />
                </View>
              ) : (
                <Row
                  first={i === 0}
                  icon="chat"
                  title={c.title}
                  subtitle={relativeTime(c.updated_at)}
                  onPress={() => onSelect(c.id)}
                  accessibilityLabel={`${c.title}, updated ${relativeTime(c.updated_at)}`}
                  trailing={
                    <View style={{ flexDirection: "row", gap: space.xs }}>
                      <IconButton name="edit" label={`Rename: ${c.title}`} onPress={() => startEditing(c)} />
                      <IconButton
                        name="wipe"
                        label={`Delete: ${c.title}`}
                        tone="critical"
                        onPress={() => confirmDelete(c.id)}
                      />
                    </View>
                  }
                />
              )}
            </View>
          ))}
        </Group>
      )}
    </View>
  );
}
