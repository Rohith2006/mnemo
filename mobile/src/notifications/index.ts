// Reminders are scheduled as local, on-device notifications the moment the
// server confirms one — no push infrastructure involved. This is what makes
// reminders work even though the backend is LAN-only: the phone alarms
// itself. Digests/nudges are NOT handled here — those are pull/in-app only,
// computed live from /api/dashboard.
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { getItem, setItem } from "../storage";
import type { ReminderOut } from "../api/types";

const SCHEDULED_MAP_KEY = "mnemo_scheduled_reminders"; // server reminder id -> local notification id

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function loadMap(): Promise<Record<string, string>> {
  const raw = await getItem(SCHEDULED_MAP_KEY);
  return raw ? JSON.parse(raw) : {};
}

async function saveMap(map: Record<string, string>): Promise<void> {
  await setItem(SCHEDULED_MAP_KEY, JSON.stringify(map));
}

export async function requestPermissions(): Promise<boolean> {
  const { status } = await Notifications.requestPermissionsAsync();
  return status === "granted";
}

export async function scheduleReminder(reminder: ReminderOut): Promise<void> {
  const fireAt = new Date(reminder.fire_at);
  if (fireAt.getTime() <= Date.now()) return; // already past, don't schedule

  const map = await loadMap();
  if (map[reminder.id]) return; // already scheduled locally, don't duplicate

  const localId = await Notifications.scheduleNotificationAsync({
    content: { title: "⏰ Reminder", body: reminder.task },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: fireAt },
  });
  map[reminder.id] = localId;
  await saveMap(map);
}

export async function cancelReminder(reminderId: string): Promise<void> {
  const map = await loadMap();
  const localId = map[reminderId];
  if (localId) {
    await Notifications.cancelScheduledNotificationAsync(localId);
    delete map[reminderId];
    await saveMap(map);
  }
}

/** Call on app foreground/launch: schedules any pending server reminder that
 * isn't already scheduled locally (covers reinstalls / a second device). */
export async function reconcile(pending: ReminderOut[]): Promise<void> {
  if (Platform.OS === "web") return; // no local notifications on web
  const granted = await requestPermissions();
  if (!granted) return;
  for (const r of pending) await scheduleReminder(r);
}
