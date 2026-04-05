import React from "react";
import { Platform } from "react-native";
import {
  AlertTriangle,
  ArrowUp,
  Bell,
  BellOff,
  Bookmark,
  BookmarkCheck,
  BookmarkMinus,
  Check,
  ChevronDown,
  Circle,
  CircleCheck,
  Flame,
  Globe,
  LayoutList,
  Lightbulb,
  LogOut,
  Mail,
  MessageSquare,
  PenLine,
  Server,
  Settings,
  Smile,
  Sunrise,
  Trash2,
  TrendingUp,
  Undo2,
  User,
  X,
} from "lucide-react-native";
import { iconSize } from "../theme";

/**
 * One icon family, one stroke width. Icons are registered by role rather than
 * by glyph name, so swapping the glyph for "a completed task" is a one-line
 * change here instead of a search across screens.
 */
const REGISTRY = {
  capture: PenLine,
  track: LayoutList,
  chat: MessageSquare,
  settings: Settings,

  fact: Bookmark,
  factUpdated: BookmarkCheck,
  factRemoved: BookmarkMinus,
  metric: TrendingUp,
  task: Circle,
  taskDone: CircleCheck,
  habit: Flame,
  mood: Smile,
  reminder: Bell,
  reminderOff: BellOff,

  briefing: Sunrise,
  insight: Lightbulb,
  alert: AlertTriangle,
  send: ArrowUp,
  check: Check,
  close: X,
  chevronDown: ChevronDown,
  undo: Undo2,

  user: User,
  email: Mail,
  timezone: Globe,
  server: Server,
  logout: LogOut,
  wipe: Trash2,
} as const;

export type IconName = keyof typeof REGISTRY;

type Props = {
  name: IconName;
  size?: number;
  color: string;
  /**
   * Only pass this when the icon stands alone. An icon next to a visible text
   * label is decorative and must stay out of the accessibility tree.
   */
  label?: string;
  fill?: string;
};

/**
 * react-native-svg renders a real <svg> on web, where the native accessibility
 * props are not valid attributes and React warns about them, so each platform
 * gets the props it actually understands.
 */
function hiddenProps() {
  if (Platform.OS === "web") return { "aria-hidden": true, focusable: false, tabIndex: -1 };
  return {
    accessible: false,
    accessibilityElementsHidden: true,
    importantForAccessibility: "no-hide-descendants" as const,
  };
}

function labelledProps(label: string) {
  if (Platform.OS === "web") return { role: "img", "aria-label": label };
  return { accessible: true, accessibilityRole: "image" as const, accessibilityLabel: label };
}

export function Icon({ name, size = iconSize.md, color, label, fill = "none" }: Props) {
  const Glyph = REGISTRY[name];
  const a11y = label ? labelledProps(label) : hiddenProps();
  return <Glyph size={size} color={color} fill={fill} strokeWidth={1.75} {...(a11y as object)} />;
}
