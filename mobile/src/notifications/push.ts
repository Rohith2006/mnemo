// Registers this device for real server-initiated push (overdue-task and
// digest alerts) — separate from index.ts, which stays the client-scheduled
// local-notification path for user-set reminders and is untouched by this.
//
// Requires the mobile project to be registered with an EAS/Expo account
// (`eas init`) — app.json needs extra.eas.projectId for getExpoPushTokenAsync
// to mint a real token. That's a one-time external setup step; without it,
// this fails silently (same posture as scheduleReminder in index.ts) rather
// than blocking login.
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { api } from "../api/client";
import { requestPermissions } from "./index";

/**
 * Never throws outward — a failed registration must not make an otherwise
 * successful login/signup look broken. Mirrors scheduleReminder's posture.
 */
export async function registerForPush(): Promise<void> {
  if (Platform.OS === "web") return; // no push support in the browser preview
  try {
    const granted = await requestPermissions();
    if (!granted) return;
    const projectId = Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
    const { data: token } = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    await api.post<void>("/api/push/register", { token, platform: Platform.OS });
  } catch (e) {
    console.warn("Could not register for push notifications", e);
  }
}
