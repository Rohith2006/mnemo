import React, { useEffect, useRef, useState } from "react";
import { Pressable, useWindowDimensions, View } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { useConversations } from "../../src/api/hooks";
import { ChatLanding } from "../../src/components/chat/ChatLanding";
import { ChatThread } from "../../src/components/chat/ChatThread";
import { ConversationList } from "../../src/components/chat/ConversationList";
import { Icon } from "../../src/components/Icon";
import { Screen, TopBar } from "../../src/components/Screen";
import { iconSize, space, useTheme } from "../../src/theme";

const WIDE_BREAKPOINT = 700;
const SIDEBAR_WIDTH = 280;

export default function ChatScreen() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= WIDE_BREAKPOINT;
  const { user } = useAuth();
  const conversationsQuery = useConversations();

  const [activeId, setActiveId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Tracks every id we've ever actually seen the server confirm, so a freshly
  // created conversation (whose id we set optimistically in onStarted, before
  // the invalidated ["conversations"] refetch has had a chance to complete)
  // isn't mistaken for one that's been deleted out from under us.
  const seenIds = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!conversationsQuery.data) return;
    for (const c of conversationsQuery.data) seenIds.current.add(c.id);
  }, [conversationsQuery.data]);

  useEffect(() => {
    if (!activeId) return;
    if (!conversationsQuery.isSuccess) return;
    const stillExists = conversationsQuery.data.some((c) => c.id === activeId);
    if (!stillExists && seenIds.current.has(activeId)) setActiveId(null);
  }, [activeId, conversationsQuery.data, conversationsQuery.isSuccess]);

  const handleSelect = (id: string) => {
    setActiveId(id);
    setDrawerOpen(false);
  };
  const handleNewChat = () => {
    setActiveId(null);
    setDrawerOpen(false);
  };

  const sidebar = (
    <ConversationList
      conversations={conversationsQuery.data ?? []}
      activeId={activeId}
      onSelect={handleSelect}
      onNewChat={handleNewChat}
    />
  );

  return (
    <Screen>
      <TopBar
        title="Chat"
        showTitle
        alwaysShowLeading
        leading={
          !isWide ? (
            <Pressable
              onPress={() => setDrawerOpen(true)}
              accessibilityRole="button"
              accessibilityLabel="Open chat history"
              hitSlop={space.md}
            >
              <Icon name="sidebar" size={iconSize.md} color={t.ink} />
            </Pressable>
          ) : undefined
        }
      />
      <View style={{ flex: 1, flexDirection: "row" }}>
        {isWide && (
          <View style={{ width: SIDEBAR_WIDTH, borderRightWidth: 1, borderRightColor: t.hairline }}>
            {sidebar}
          </View>
        )}
        <View style={{ flex: 1 }}>
          {activeId ? (
            <ChatThread key={activeId} conversationId={activeId} />
          ) : (
            <ChatLanding
              userName={user?.name ?? ""}
              tz={user?.tz ?? "Asia/Kolkata"}
              onStarted={setActiveId}
            />
          )}
        </View>
      </View>

      {!isWide && drawerOpen && (
        <>
          <Pressable
            onPress={() => setDrawerOpen(false)}
            accessibilityRole="button"
            accessibilityLabel="Close chat history"
            style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: t.overlay }}
          />
          <View
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              bottom: 0,
              width: SIDEBAR_WIDTH,
              backgroundColor: t.canvas,
              borderRightWidth: 1,
              borderRightColor: t.hairline,
            }}
          >
            {sidebar}
          </View>
        </>
      )}
    </Screen>
  );
}
