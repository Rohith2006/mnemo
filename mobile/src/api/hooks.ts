import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { CaptureResponse, ChatMessage, ChatResponse, DashboardOut, DigestOut, HabitOut, TaskOut } from "./types";
import { scheduleReminder, cancelReminder as cancelLocalReminder } from "../notifications";

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<DashboardOut>("/api/dashboard") });
}

export function useCapture() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => api.post<CaptureResponse>("/api/capture", { text }),
    onSuccess: async (res) => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (res.reminder) await scheduleReminder(res.reminder);
    },
  });
}

export function useChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ message, history }: { message: string; history: ChatMessage[] }) =>
      api.post<ChatResponse>("/api/chat", { message, history }),
    onSuccess: async (res) => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (res.reminder) await scheduleReminder(res.reminder);
    },
  });
}

export function useCompleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<TaskOut>(`/api/tasks/${id}/complete`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useAddTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (task: string) => api.post<TaskOut[]>("/api/tasks", { task }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useLogHabit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.post<HabitOut>(`/api/habits/${encodeURIComponent(name)}/log`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useDigest(kind: "morning" | "evening" | "ondemand") {
  const qc = useQueryClient();
  return useMutation<DigestOut, Error, boolean>({
    mutationFn: (refresh) => api.get<DigestOut>(`/api/digests/${kind}${refresh ? "?refresh=true" : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useCancelReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/reminders/${id}`),
    onSuccess: async (_data, id) => {
      await cancelLocalReminder(id);
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useForget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/api/forget"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}
