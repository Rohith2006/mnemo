import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, useWindowDimensions, View } from "react-native";
import {
  useCancelReminder,
  useCompleteTask,
  useDashboard,
  useLogHabit,
  useReopenTask,
} from "../../src/api/hooks";
import { IconButton } from "../../src/components/Button";
import { Icon } from "../../src/components/Icon";
import { Chip, EmptyRow, Group, GroupFootnote, Row, SectionHeader } from "../../src/components/List";
import { contentPadding, LargeTitle, Screen, TopBar, useScrollHeader } from "../../src/components/Screen";
import { Card, Stat } from "../../src/components/Surfaces";
import { Text } from "../../src/components/Text";
import { iconSize, space, useTheme } from "../../src/theme";

export default function TrackScreen() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const pad = contentPadding(width);
  const { scrolled, scrollProps } = useScrollHeader();
  const [showCompleted, setShowCompleted] = useState(false);

  const { data: dash, refetch, isRefetching } = useDashboard();
  const completeTask = useCompleteTask();
  const cancelReminder = useCancelReminder();
  const logHabit = useLogHabit();
  const reopenTask = useReopenTask();

  return (
    <Screen>
      <TopBar title="Track" showTitle={scrolled} />
      <ScrollView
        {...scrollProps}
        contentContainerStyle={{ paddingHorizontal: pad, paddingTop: space.xxl, paddingBottom: space.huge }}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={t.inkFaint} />
        }
      >
        <LargeTitle title="Track" subtitle="What mnemo has kept so far." />

        <Section title="Profile">
          {dash?.profile.length ? (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm }}>
              {dash.profile.map((f, i) => (
                <Chip key={i}>{f}</Chip>
              ))}
            </View>
          ) : (
            <Text variant="callout" tone="faint">
              Nothing learned about you yet.
            </Text>
          )}
        </Section>

        <Section title="Habits">
          <Group>
            {dash?.habits.length ? (
              dash.habits.map((h, i) => (
                <Row
                  key={h.name}
                  first={i === 0}
                  icon="habit"
                  iconColor={h.streak > 0 ? t.positive : t.inkFaint}
                  title={h.name}
                  // The best run is only worth saying when it is not the current one.
                  subtitle={h.best_streak > h.streak ? `Best run ${h.best_streak}` : undefined}
                  value={`${h.streak}d`}
                  valueTone={h.streak > 0 ? "positive" : "muted"}
                  valueMono
                  onPress={() => logHabit.mutate(h.name)}
                  accessibilityLabel={`${h.name}, ${h.streak} day streak. Log as done today.`}
                />
              ))
            ) : (
              <EmptyRow>No habits yet. Mention one in Capture and it starts counting.</EmptyRow>
            )}
          </Group>
          {!!dash?.habits.length && <GroupFootnote>Tap a habit to log it for today.</GroupFootnote>}
        </Section>

        <Section title="Open tasks">
          <Group>
            {dash?.tasks.length ? (
              dash.tasks.map((task, i) => {
                const due = dueState(task.due);
                return (
                  <Row
                    key={task.id}
                    first={i === 0}
                    icon="task"
                    title={task.task}
                    value={due.label}
                    valueTone={due.tone}
                    onPress={() => completeTask.mutate(task.id)}
                    accessibilityLabel={`${task.task}. Mark complete.`}
                  />
                );
              })
            ) : (
              <EmptyRow>Nothing open.</EmptyRow>
            )}
          </Group>
          {!!dash?.tasks.length && <GroupFootnote>Tap a task to mark it complete.</GroupFootnote>}
        </Section>

        {!!dash?.completed.length && (
          <View style={{ marginBottom: space.xxxl }}>
            <Pressable
              onPress={() => setShowCompleted((v) => !v)}
              accessibilityRole="button"
              accessibilityLabel={`Completed, ${dash.completed.length} tasks. ${showCompleted ? "Collapse" : "Expand"}.`}
              style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
            >
              <SectionHeader
                title="Completed"
                trailing={
                  <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                    <Text variant="mono" tone="faint">
                      {dash.completed.length}
                    </Text>
                    <View style={{ transform: [{ rotate: showCompleted ? "180deg" : "0deg" }] }}>
                      <Icon name="chevronDown" size={iconSize.sm} color={t.inkFaint} />
                    </View>
                  </View>
                }
              />
            </Pressable>
            {showCompleted && (
              <>
                <Group>
                  {dash.completed.map((task, i) => (
                    <Row
                      key={task.id}
                      first={i === 0}
                      icon="taskDone"
                      iconColor={t.positive}
                      title={task.task}
                      subtitle={doneLabel(task.done_at)}
                      trailing={
                        <IconButton
                          name="undo"
                          label={`Move back to open: ${task.task}`}
                          onPress={() => reopenTask.mutate(task.id)}
                        />
                      }
                    />
                  ))}
                </Group>
                <GroupFootnote>Tap the undo icon to move a task back to open.</GroupFootnote>
              </>
            )}
          </View>
        )}

        {!!dash?.trends.length && (
          <Section title="Trends">
            <Card style={{ padding: space.lg, gap: space.xs }}>
              {dash.trends.map((tr, i) => (
                <Text key={i} variant="mono" tone="muted">
                  {tr}
                </Text>
              ))}
            </Card>
          </Section>
        )}

        {!!dash?.mood && (
          <Section title="Mood, last 7 days">
            <Card>
              <Stat
                value={String(dash.mood.avg)}
                suffix="out of 10"
                ratio={dash.mood.avg / 10}
                caption={`${dash.mood.count} ${dash.mood.count === 1 ? "entry" : "entries"} recorded`}
              />
            </Card>
          </Section>
        )}

        {!!dash?.reminders.length && (
          <Section title="Reminders">
            <Group>
              {dash.reminders.map((r, i) => (
                <Row
                  key={r.id}
                  first={i === 0}
                  icon="reminder"
                  title={r.task}
                  value={fireAt(r.fire_at)}
                  valueMono
                  trailing={
                    <IconButton
                      name="reminderOff"
                      label={`Cancel reminder: ${r.task}`}
                      onPress={() => cancelReminder.mutate(r.id)}
                    />
                  }
                />
              ))}
            </Group>
          </Section>
        )}

        {!dash && (
          <View style={{ alignItems: "center", marginTop: space.huge, gap: space.sm }}>
            <Icon name="track" size={iconSize.lg} color={t.inkFaint} />
            <Text variant="callout" tone="faint">
              Loading what mnemo remembers.
            </Text>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: space.xxxl }}>
      <SectionHeader title={title} />
      {children}
    </View>
  );
}

/** Due dates earn colour only once they actually mean something. */
function dueState(due: string | null): { label: string; tone: "muted" | "caution" | "critical" } {
  if (!due) return { label: "", tone: "muted" };

  if (!due.includes("T")) {
    // Date-only due ("YYYY-MM-DD"): `new Date(due)` parses this as UTC midnight,
    // which flags a same-day task as overdue hours before local midnight. Compare
    // calendar days instead, so only a day that's fully passed counts as overdue —
    // no time was given, so there's nothing to be overdue by within today.
    const m = due.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return { label: due.slice(0, 10), tone: "muted" };
    const at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayDiff = Math.round((at.getTime() - today.getTime()) / 86_400_000);
    const label = at.toLocaleDateString([], { month: "short", day: "numeric" });
    if (dayDiff < 0) return { label: `${label}, overdue`, tone: "critical" };
    if (dayDiff <= 1) return { label, tone: "caution" };
    return { label, tone: "muted" };
  }

  const at = new Date(due);
  if (Number.isNaN(at.getTime())) return { label: due.slice(0, 10), tone: "muted" };

  const hours = (at.getTime() - Date.now()) / 3_600_000;
  const label = at.toLocaleDateString([], { month: "short", day: "numeric" });
  if (hours < 0) return { label: `${label}, overdue`, tone: "critical" };
  if (hours < 24) return { label, tone: "caution" };
  return { label, tone: "muted" };
}

function doneLabel(doneAt: string | null): string | undefined {
  if (!doneAt) return undefined;
  const at = new Date(doneAt);
  if (Number.isNaN(at.getTime())) return undefined;
  return `Completed ${at.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

function fireAt(iso: string) {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
