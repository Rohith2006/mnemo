// Time-of-day-aware, randomly-picked greeting for the Chat landing state.
// The bucket is computed from the ACCOUNT's stored timezone, never the
// device's local clock — the due-date bug earlier in this project came from
// exactly that kind of local-time assumption, and it must not repeat here.

export type GreetingBucket = "night" | "morning" | "afternoon" | "evening";

const POOL: Record<GreetingBucket, string[]> = {
  night: ["Still up, {name}?", "Burning the midnight oil, {name}?"],
  morning: ["Good morning, {name}!", "Rise and shine, {name}."],
  afternoon: ["Good afternoon, {name}!", "Back at it, {name}!"],
  evening: ["Good evening, {name}!", "Evening, {name}."],
};

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
  const pool = POOL[bucket];
  const template = pool[Math.floor(Math.random() * pool.length)];
  const firstName = (name || "").trim().split(/\s+/)[0] || "there";
  return template.replace("{name}", firstName);
}
