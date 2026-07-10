// Time-of-day-aware, randomly-picked greeting for the Chat landing state.
// The bucket is computed from the ACCOUNT's stored timezone, never the
// device's local clock — the due-date bug earlier in this project came from
// exactly that kind of local-time assumption, and it must not repeat here.

export type GreetingBucket = "night" | "morning" | "afternoon" | "evening";

const POOL: Record<GreetingBucket, string[]> = {
  night: [
    "Still up, {name}?",
    "Burning the midnight oil, {name}?",
    "Can't sleep, {name}?",
    "Late one tonight, {name}.",
    "Night owl mode, {name}?",
  ],
  morning: [
    "Good morning, {name}!",
    "Rise and shine, {name}.",
    "Morning, {name} — ready when you are.",
    "Top of the morning, {name}.",
    "Let's start the day, {name}.",
  ],
  afternoon: [
    "Good afternoon, {name}!",
    "Back at it, {name}!",
    "Afternoon, {name}.",
    "How's the day treating you, {name}?",
    "Midday check-in, {name}?",
  ],
  evening: [
    "Good evening, {name}!",
    "Evening, {name}.",
    "Winding down, {name}?",
    "How was your day, {name}?",
    "Evening, {name} — what's on your mind?",
  ],
};

// Carry no time-of-day claim, so they're safe to surface at any hour —
// this is the pool the user specifically asked to have expanded, as
// opposed to the time-bucketed ones above.
const GENERIC: string[] = [
  "Welcome back, {name}.",
  "Good to see you, {name}.",
  "Picking up where we left off, {name}.",
  "Hi {name}, what's on your mind?",
  "Ready when you are, {name}.",
  "{name}, what should we remember today?",
  "Hey {name} — what are we working on?",
  "Glad you're here, {name}.",
  "Let's pick this up, {name}.",
  "What can I help you keep track of, {name}?",
  "Hey {name}, good to have you back.",
  "{name}! What's going on today?",
];

/** Buckets, by local hour in the given tz: night 0-4, morning 5-11, afternoon 12-16, evening 17-23. */
export function bucketForHour(hour: number): GreetingBucket {
  if (hour < 5) return "night";
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

export function hourInTimeZone(tz: string, at: Date = new Date()): number {
  // hourCycle: "h23" explicitly avoids the "24 instead of 0 at midnight" quirk
  // some engines produce with hour12: false instead.
  const formatter = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "numeric", hourCycle: "h23" });
  return parseInt(formatter.format(at), 10);
}

export function randomGreeting(tz: string, name: string): string {
  const bucket = bucketForHour(hourInTimeZone(tz));
  // Every generic line is time-agnostic by construction, so mixing them into
  // the bucket-specific pool can never surface a wrong-time-of-day claim.
  const pool = [...POOL[bucket], ...GENERIC];
  const template = pool[Math.floor(Math.random() * pool.length)];
  const firstName = (name || "").trim().split(/\s+/)[0] || "there";
  return template.replace("{name}", firstName);
}
