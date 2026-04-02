# Chats feature — persistent, multi-conversation Chat tab

Status: approved by user, ready for implementation planning.

## Context

Today, `mobile/app/(tabs)/chat.tsx` holds conversation state entirely client-side
(`useState<Bubble[]>([])`), lost on navigation away/app restart. `POST /api/chat`
is stateless per turn: the client resends its entire local history array every
call, and the server never persists it anywhere. There is no concept of "a
conversation" as a named, listable, revisitable thing.

This spec adds real persistence and a multi-conversation UI: a chat list
("sidebar" on wide screens, a drawer on phone-width screens), a "New chat"
entry point with a Claude-style greeting landing state, and rename/delete on
individual conversations.

Out of scope (deferred, separate future spec, per user's own sequencing):
viewing/editing/deleting the *extracted* personal data (facts, logs, tasks,
habits) mnemo has stored about the user. That is a different subsystem and
gets its own spec.

## Data model

Two new tables in `db.py`, following the existing schema conventions (`id`
via `_sid()`-style hex uuid, ISO-string timestamps, per-user scoping):

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,       -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages(conversation_id, created_at);
```

A conversation is created **lazily**: opening "New chat" does not write a row.
The first message sent from that composer creates the conversation (title
derived from that message, truncated to ~50 chars on a word boundary +
ellipsis if cut) and the first `chat_messages` row, in the same request.

`UserStore.forget_all()` (the "Erase everything" wipe) must also delete from
`conversations` and `chat_messages` — chat history is personal data like
everything else it already wipes.

## Backend API

All new methods live on `UserStore` in `store.py` (not a separate store
class), matching how tasks/habits/facts already work — a conversation belongs
to a user the same way.

- `UserStore.create_conversation(title, first_message) -> dict` — inserts the
  conversation + its first message, returns the conversation with id.
- `UserStore.list_conversations() -> list[dict]` — `{id, title, updated_at}`,
  most-recently-updated first.
- `UserStore.conversation_messages(conversation_id) -> list[dict]` — full
  thread in order, or `[]` if the id doesn't belong to this user (never leak
  another user's conversation).
- `UserStore.add_message(conversation_id, role, content) -> None` — appends
  and bumps `updated_at`.
- `UserStore.rename_conversation(conversation_id, title) -> dict | None`.
- `UserStore.delete_conversation(conversation_id) -> bool`.

**`POST /api/chat`** (`api/routers/chat.py`) changes shape:
- Request gains `conversation_id: str | None = None`. The `history` field is
  **removed** — the server now owns history, never trusts client-resent
  history again.
- If `conversation_id` is `None`: create a new conversation lazily (as
  above), using this message as both the first turn and the title source.
- If provided: load that conversation's messages from the DB for context,
  append the new user message.
- Feeds `build_reply` only the **last 20 messages** (individual rows, user
  and assistant turns combined — i.e. the 20 most recent `chat_messages`
  rows, not 20 exchanges) of the conversation, not the full thread — bounds
  token usage on a long-running chat. The full thread is still stored and
  shown in the UI; this cap only affects what goes into the LLM call.
- Response gains `conversation_id: str` (the id the client should remember,
  whether newly created or the one passed in) so the client can attach
  follow-up turns to the same thread.
- Still runs `detect_reminder` + `extract`/`apply_extraction` exactly as
  today — unchanged.

New endpoints (`api/routers/conversations.py`):
- `GET /api/conversations` → list for the sidebar.
- `GET /api/conversations/{id}/messages` → full thread, 404 if not found/not
  owned by the caller.
- `PATCH /api/conversations/{id}` (`{title}`) → rename, 404 if not found.
- `DELETE /api/conversations/{id}` → 204, 404 if not found.

## Mobile UI

**Layout, responsive:**
- Wide (existing `contentPadding` breakpoint, ≥700px): permanent left column
  (chat list + "New chat" at top) alongside the main chat area on the right —
  like Claude's web app.
- Narrow (phone width): the list becomes a slide-in drawer, opened by a menu
  icon in the top-left of the Chat tab's `TopBar` (mirroring how the
  ChatGPT/Claude *mobile* apps do this, not their desktop layout). Selecting
  an item or "New chat" closes the drawer; tapping the scrim behind it also
  closes it. No swipe gesture required — keep it simple.
- Same list component and same data in both cases — only the container
  (fixed column vs. drawer) differs by width.

**Landing state** (no conversation open — the default when the tab first
loads, and after tapping "New chat"):
- Centered, animated `MnemoMark` — a slow, subtle breathing scale/opacity
  loop (`Animated.loop`), respecting `AccessibilityInfo.isReduceMotionEnabled()`
  the same way `Receipt.tsx` already does for its own animation.
- A greeting line below it, randomly chosen (re-rolled every visit) from a
  pool bucketed by time of day, computed from **the account's stored `tz`**
  (already fetched via `/api/me`, already used for every other date
  computation in this app), never raw device time. This is deliberate: the
  due-date bug earlier this session came from exactly this kind of
  local-time assumption, and it must not repeat here. Buckets, by the local
  hour in that tz: night `0–4`, morning `5–11`, afternoon `12–16`, evening
  `17–23`. Sample pool (first name interpolated from `/api/me`'s `name`):
  - Night: "Still up, {name}?", "Burning the midnight oil, {name}?"
  - Morning: "Good morning, {name}!", "Rise and shine, {name}."
  - Afternoon: "Good afternoon, {name}!", "Back at it, {name}!"
  - Evening: "Good evening, {name}!", "Evening, {name}."
- A centered composer textbox below the greeting; sending a message here is
  what actually creates the conversation (per the lazy-creation design) and
  transitions the screen into thread view.

**Thread view** (a conversation is open): same message-bubble list as today,
now hydrated from `GET /api/conversations/{id}/messages` on open instead of
local-only state; composer pinned at the bottom with the Enter-sends /
Shift+Enter-newline behavior already implemented.

**Sidebar/drawer list item:** title + a short relative timestamp on
`updated_at` — "Just now" under a minute, "12m ago" / "3h ago" under a day,
then a short date ("29 Aug") beyond that, mirroring the date-label style
`track.tsx` already uses elsewhere in the app. Two per-item actions: rename
(inline edit) and delete. Delete shows a confirmation dialog
before removing anything — using the same `Platform.OS === "web" ?
window.confirm(...) : Alert.alert(...)` branch already fixed in
`settings.tsx`'s "Erase everything" (since `Alert.alert` is a documented
no-op on `react-native-web`).

## Data flow summary

1. User opens Chat tab → landing state shown, greeting rolled once.
2. User types and sends → `POST /api/chat` with no `conversation_id` →
   server creates conversation + message, calls `build_reply`, returns
   `{reply, conversation_id, reminder}`.
3. Client stores `conversation_id`, switches to thread view, appends the
   reply bubble.
4. Subsequent sends in the same thread pass that `conversation_id`; server
   loads history from DB (capped to last 20 for the LLM call), appends both
   turns, bumps `updated_at`.
5. Opening an old conversation from the list: `GET
   /api/conversations/{id}/messages`, render as thread, continue sending with
   that `conversation_id`.
6. Rename/delete hit their endpoints directly and refresh the list.

## Testing

Backend: store-level tests for each new `UserStore` method (create, list
ordering, message ordering, rename, delete, cross-user isolation — a
conversation/messages call must never return another user's data) and
API-level tests for the new/changed endpoints, following the existing
`tests/test_store.py` / `tests/test_api.py` patterns (isolated tmp-path DB,
mocked `call_llm`). Mobile: `tsc --noEmit` clean; manual verification through
the browser preview (signup → new chat → send → reopen from list → rename →
delete) the way every other feature this session was verified, since there is
no mobile test suite yet.
