// Reminders are scheduled as local, on-device notifications the moment the
// server confirms one, with no push infrastructure involved. This is what makes
// reminders work even though the backend is LAN-only: the phone alarms
// itself. Digests/nudges are NOT handled here: those are pull/in-app only,
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

/**
 * Never throws. The server is the source of truth for a reminder, so failing to
 * set the local alarm (no web support, permission denied, OS quota) must not
 * make an otherwise successful capture look like it failed. `reconcile` picks
 * up anything that did not get scheduled the next time the dashboard loads.
 */
export async function scheduleReminder(reminder: ReminderOut): Promise<boolean> {
  if (Platform.OS === "web") return false; // no local notifications on web

  const fireAt = new Date(reminder.fire_at);
  if (fireAt.getTime() <= Date.now()) return false; // already past, don't schedule

  try {
    const map = await loadMap();
    if (map[reminder.id]) return true; // already scheduled locally, don't duplicate

    const localId = await Notifications.scheduleNotificationAsync({
      content: { title: "Reminder", body: reminder.task },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: fireAt },
    });
    map[reminder.id] = localId;
    await saveMap(map);
    return true;
  } catch (e) {
    console.warn("Could not schedule a local reminder notification", e);
    return false;
  }
}

export async function cancelReminder(reminderId: string): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    const map = await loadMap();
    const localId = map[reminderId];
    if (localId) {
      await Notifications.cancelScheduledNotificationAsync(localId);
      delete map[reminderId];
      await saveMap(map);
    }
  } catch (e) {
    console.warn("Could not cancel a local reminder notification", e);
  }
}

/** Call on app foreground/launch: schedules any pending server reminder that
 * isn't already scheduled locally (covers reinstalls / a second device). */
export async function reconcile(pending: ReminderOut[]): Promise<void> {
  if (Platform.OS === "web") return; // no local notifications on web
  try {
    const granted = await requestPermissions();
    if (!granted) return;
  } catch {
    return;
  }
  for (const r of pending) await scheduleReminder(r);
}
