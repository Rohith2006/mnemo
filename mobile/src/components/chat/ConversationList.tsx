import React, { useState } from "react";
import { Alert, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import { useDeleteConversation, useRenameConversation } from "../../api/hooks";
import type { ConversationOut } from "../../api/types";
import { Icon } from "../Icon";
import { IconButton } from "../Button";
import { EmptyRow } from "../List";
import { Text } from "../Text";
import { iconSize, radius, space, type as typeScale, useTheme } from "../../theme";

// No `(hover: hover)` match means a touch-only device (or the native app,
// where `window` doesn't exist at all) — there, hover can never reveal the
// row actions, so they stay visible all the time instead.
const HOVER_CAPABLE =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(hover: hover)").matches
    : false;

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
        style={({ pressed, hovered }: any) => ({
          flexDirection: "row",
          alignItems: "center",
          gap: space.sm,
          padding: space.md,
          borderRadius: radius.md,
          backgroundColor: pressed || hovered ? t.sunken : "transparent",
          marginBottom: space.sm,
        })}
      >
        <Icon name="newChat" size={iconSize.sm} color={t.ink} />
        <Text variant="bodyMedium">New chat</Text>
      </Pressable>

      {conversations.length === 0 ? (
        <EmptyRow>No chats yet. Send a message to start one.</EmptyRow>
      ) : (
        <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
          {conversations.map((c) =>
            editingId === c.id ? (
              <View
                key={c.id}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: space.sm,
                  paddingVertical: space.sm,
                  paddingHorizontal: space.md,
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
              <ConversationRow
                key={c.id}
                conversation={c}
                active={c.id === activeId}
                onSelect={() => onSelect(c.id)}
                onEdit={() => startEditing(c)}
                onDelete={() => confirmDelete(c.id)}
              />
            ),
          )}
        </ScrollView>
      )}
    </View>
  );
}

// Deliberately not the shared `Row` component: that renders its `onPress`
// wrapper with accessibilityRole="button", and nesting `trailing`'s own
// IconButtons (each a real <button> on web) inside another <button> is
// invalid HTML — confirmed live as the exact console errors this row used
// to throw. Structuring the select-area and the actions as siblings, not
// parent/child, avoids the nesting entirely.
function ConversationRow({
  conversation,
  active,
  onSelect,
  onEdit,
  onDelete,
}: {
  conversation: ConversationOut;
  active: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const t = useTheme();
  const [hovered, setHovered] = useState(false);
  const showActions = !HOVER_CAPABLE || hovered;
  // A plain View with raw DOM mouse events, not another Pressable: RNW's
  // Pressable/useHover uses a "contain" lock — hovering the nested
  // select-Pressable below dispatches a lock event that immediately ends
  // hover on any ancestor Pressable, so tracking hover on an outer
  // Pressable here would flicker off the moment the pointer reached the
  // title text. Raw onMouseEnter/onMouseLeave aren't part of that scheme.
  const hoverProps =
    Platform.OS === "web" ? ({ onMouseEnter: () => setHovered(true), onMouseLeave: () => setHovered(false) } as any) : null;
  return (
    <View style={{ marginBottom: 2 }}>
      <View
        {...hoverProps}
        style={{
          flexDirection: "row",
          alignItems: "center",
          borderRadius: radius.md,
          backgroundColor: active || hovered ? t.sunken : "transparent",
        }}
      >
        <Pressable
          onPress={onSelect}
          accessibilityRole="button"
          accessibilityLabel={`${conversation.title}, open conversation`}
          style={{
            flex: 1,
            flexDirection: "row",
            alignItems: "center",
            gap: space.sm,
            paddingVertical: space.sm,
            paddingHorizontal: space.md,
            minWidth: 0,
          }}
        >
          <Icon name="chat" size={iconSize.sm} color={t.inkFaint} />
          <Text variant="body" numberOfLines={1} style={{ flex: 1 }}>
            {conversation.title}
          </Text>
        </Pressable>
        <View
          style={[
            { flexDirection: "row", paddingRight: space.xs, opacity: showActions ? 1 : 0 },
            { transitionProperty: "opacity", transitionDuration: "120ms" } as object,
          ]}
        >
          <IconButton name="edit" label={`Rename: ${conversation.title}`} onPress={onEdit} />
          <IconButton name="wipe" label={`Delete: ${conversation.title}`} tone="critical" onPress={onDelete} />
        </View>
      </View>
    </View>
  );
}
