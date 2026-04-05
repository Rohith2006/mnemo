// Mirrors api/schemas.py on the backend.

export type UserOut = {
  user_id: string;
  email: string;
  name: string;
  tz: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: UserOut;
};

export type ReminderOut = {
  id: string;
  task: string;
  fire_at: string; // ISO8601
};

export type CaptureResponse = {
  facts: string[];
  facts_updated: string[];
  facts_removed: string[];
  log: { category: string; key: string; value: unknown; unit: string; note: string; at: string }[];
  tasks: { id: string; task: string; due: string | null; status: string }[];
  done: { id: string; task: string; status: string }[];
  habits: { id?: string; name: string; streak: number; best_streak: number; _status?: string }[];
  mood: { id: string; mood: number; note: string } | null;
  reminder: ReminderOut | null;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type ChatResponse = {
  reply: string;
  reminder: ReminderOut | null;
};

export type TaskOut = {
  id: string;
  task: string;
  due: string | null;
  status: string;
  done_at: string | null;
};

export type HabitOut = {
  name: string;
  streak: number;
  best_streak: number;
  last_done: string | null;
};

export type LogEntryOut = {
  category: string;
  key: string;
  value: string | null;
  unit: string;
};

export type MoodOut = {
  avg: number;
  count: number;
};

export type DashboardOut = {
  profile: string[];
  habits: HabitOut[];
  tasks: TaskOut[];
  completed: TaskOut[];
  trends: string[];
  log: LogEntryOut[];
  mood: MoodOut | null;
  reminders: ReminderOut[];
  alerts: string[];
};

export type DigestOut = {
  kind: string;
  text: string;
  date: string;
};
