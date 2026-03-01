import React from "react";
import { RefreshControl, ScrollView, useWindowDimensions, View } from "react-native";
import { useCancelReminder, useCompleteTask, useDashboard, useLogHabit } from "../../src/api/hooks";
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

  const { data: dash, refetch, isRefetching } = useDashboard();
  const completeTask = useCompleteTask();
  const cancelReminder = useCancelReminder();
  const logHabit = useLogHabit();

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
  const at = new Date(due);
  if (Number.isNaN(at.getTime())) return { label: due.slice(0, 10), tone: "muted" };

  const hours = (at.getTime() - Date.now()) / 3_600_000;
  const label = at.toLocaleDateString([], { month: "short", day: "numeric" });
  if (hours < 0) return { label: `${label}, overdue`, tone: "critical" };
  if (hours < 24) return { label, tone: "caution" };
  return { label, tone: "muted" };
}

function fireAt(iso: string) {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
