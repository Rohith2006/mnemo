"""
Proactive Personal Assistant (Telegram)

A PA that doesn't just reply — it tracks everything it can, spots patterns, and
reaches out on its own:

  • Structured, trend-aware memory   (profile / log / tasks / habits / mood)
  • Auto-extraction every turn        (one structured LLM call → all buckets)
  • Morning briefing + evening review (per-user, in their timezone)
  • Smart nudges                      (streak-at-risk, due/overdue tasks; rate-limited)
  • NLP reminders                     (natural language → scheduled message)

Shares its brain (brain.py) and memory (store.py) with the web UI (web.py) —
no separate LLM client or duplicated extraction logic here.

Run:   python pa.py
Needs: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY/ANTHROPIC_BASE_URL (see .env.example)
"""

import os
import re
import asyncio
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, BotCommand, MenuButtonCommands
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

import brain
from brain import extract, apply_extraction, detect_reminder, build_digest, human_duration
from store import get_store, registry, reminder_store, DEFAULT_TZ

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


# ── Reminder scheduling ─────────────────────────────────────────────────────
async def fire_reminder(app: Application, rid: str, chat_id: int, task: str) -> None:
    try:
        await app.bot.send_message(chat_id, f"⏰ *Reminder\\!*\n\n{escape_md(task)}", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await app.bot.send_message(chat_id, f"⏰ Reminder: {task}")
    reminder_store.remove(rid)


async def _reminder_task(app, rid, chat_id, task, fire_at):
    delay = max(0.0, (fire_at - datetime.now().astimezone()).total_seconds())
    await asyncio.sleep(delay)
    await fire_reminder(app, rid, chat_id, task)


def schedule_reminder(app, rid, chat_id, task, fire_at):
    asyncio.create_task(_reminder_task(app, rid, chat_id, task, fire_at))


# ── Chat ────────────────────────────────────────────────────────────────────
async def chat(user_id: str, user_message: str, history: list[dict], app: Application, chat_id: int) -> str:
    tz = registry.tz(user_id)
    store = get_store(user_id)

    pending = reminder_store.get_all_for_chat(chat_id)
    if pending:
        r_lines = [f'  - "{r["task"]}" fires {r["fire_at_dt"].astimezone(tz).strftime("%H:%M on %a %d %b")}' for r in pending]
        reminders_block = "PENDING REMINDERS (already scheduled):\n" + "\n".join(r_lines)
    else:
        reminders_block = "PENDING REMINDERS: none."

    reminder = detect_reminder(user_message, tz)

    system_prompt = (
        f"You are a warm, proactive personal assistant on Telegram. It is "
        f"{datetime.now(tz).strftime('%A %H:%M')} for the user.\n"
        "You actively track the user's life and help them stay organized. You have a REAL reminder "
        "system and send scheduled messages — NEVER say you can't track time or set reminders.\n"
        "Use what you know to personalize, give concrete suggestions, and gently coach — but NEVER "
        "fabricate facts. When the user shares info, acknowledge it warmly. Markdown is allowed.\n\n"
        f"=== WHAT YOU KNOW ===\n{store.summary()}\n=====================\n\n"
        f"=== {reminders_block}\n====================="
    )
    if reminder:
        fire_local = (datetime.now().astimezone() + timedelta(seconds=reminder["seconds"])).astimezone(tz)
        system_prompt += (
            f"\n\nSYSTEM ACTION: reminder saved — \"{reminder['task']}\" fires in "
            f"{human_duration(reminder['seconds'])} at {fire_local.strftime('%H:%M')}. Confirm it."
        )

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
    reply = brain.call_llm(messages, temperature=0.7, max_tokens=1024)

    if reminder:
        fire_at = datetime.now().astimezone() + timedelta(seconds=reminder["seconds"])
        rid = reminder_store.add(chat_id, reminder["task"], fire_at)
        schedule_reminder(app, rid, chat_id, reminder["task"], fire_at)

    # Track everything from this turn.
    apply_extraction(store, extract(user_message, reply, store, tz))
    return reply


# ── Proactive engine ────────────────────────────────────────────────────────
async def send_digest(app: Application, user_id: str, kind: str):
    u = registry.get(user_id)
    if not u or u.get("paused") or not u.get("chat_id"):
        return
    tz = registry.tz(user_id)
    store = get_store(user_id)
    # Skip an empty morning/evening message for brand-new users.
    if not store.facts() and not store.open_tasks() and not store.active_habits() and not store.recent_log(2):
        return
    header = {"morning": "☀️ *Morning briefing*", "evening": "🌙 *Evening review*"}.get(kind, "💡 *Update*")
    try:
        text = build_digest(store, tz, kind)
        await send_text(app, u["chat_id"], f"{header}\n\n{text}")
    except Exception as e:
        print(f"[digest] {user_id} {kind} failed: {e}")


async def morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    await send_digest(context.application, context.job.data, "morning")


async def evening_review(context: ContextTypes.DEFAULT_TYPE):
    await send_digest(context.application, context.job.data, "evening")


async def nudge_sweep(context: ContextTypes.DEFAULT_TYPE):
    """Hourly, code-driven, rate-limited. Sends at most the single most urgent nudge."""
    app = context.application
    for user_id in list(registry.all().keys()):
        if not registry.can_nudge(user_id):
            continue
        u = registry.get(user_id)
        tz = registry.tz(user_id)
        now = datetime.now(tz)
        if now.hour < 8 or now.hour >= 22:  # quiet hours
            continue
        store = get_store(user_id)

        msg = None
        overdue = store.overdue_tasks(tz)
        due_soon = store.tasks_due_within(3, tz)
        at_risk = store.habits_at_risk(tz)

        if overdue:
            t = overdue[0]
            msg = f"📌 Heads up — *{escape_md(t['task'])}* was due {escape_md(t['due_dt'].strftime('%H:%M %a'))}\\. Done, or reschedule?"
        elif due_soon:
            t = due_soon[0]
            msg = f"⏳ *{escape_md(t['task'])}* is due at {escape_md(t['due_dt'].strftime('%H:%M'))}\\."
        elif now.hour >= 18 and at_risk:
            h = max(at_risk, key=lambda x: x.get("streak", 0))
            if h.get("streak", 0) >= 2:
                msg = f"🔥 Your *{escape_md(h['name'])}* streak is at day {h['streak']} — don't break it today\\!"

        if msg:
            try:
                await app.bot.send_message(u["chat_id"], msg, parse_mode=ParseMode.MARKDOWN_V2)
                registry.record_nudge(user_id)
            except Exception as e:
                print(f"[nudge] {user_id} failed: {e}")


def schedule_user_jobs(app: Application, user_id: str):
    """(Re)schedule per-user morning/evening digests in the user's timezone."""
    jq = app.job_queue
    u = registry.get(user_id)
    if not u:
        return
    tz = ZoneInfo(u.get("tz", DEFAULT_TZ))
    for prefix, cb, default in (("morning", morning_briefing, "08:00"), ("evening", evening_review, "21:00")):
        name = f"{prefix}:{user_id}"
        for j in jq.get_jobs_by_name(name):
            j.schedule_removal()
        hh, mm = (u.get(prefix, default).split(":") + ["0"])[:2]
        jq.run_daily(cb, time=dtime(int(hh), int(mm), tzinfo=tz), data=user_id, name=name)


# ── Telegram formatting ──────────────────────────────────────────────────────
def escape_md(text: str) -> str:
    return re.sub(r"([\\_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def format_ai_response(text: str) -> str:
    lines, out = text.split("\n"), []
    in_code, lang, code = False, "", []
    for line in lines:
        if line.startswith("```"):
            if in_code:
                out.append(f"```{lang}\n" + "\n".join(code) + "\n```")
                code, lang, in_code = [], "", False
            else:
                in_code, lang = True, line[3:].strip()
            continue
        if in_code:
            code.append(line)
            continue
        e = escape_md(line)
        if re.match(r"^\\#+ ", e):
            e = f"*{re.sub(r'^(\\#)+ ', '', e)}*"
        elif e.startswith(r"\- ") or e.startswith(r"\* "):
            e = f"• {e[3:]}"
        e = re.sub(r"\*\*(.+?)\*\*", r"*\1*", e)
        e = re.sub(r"(?<!\w)\_(.+?)\_(?!\w)", r"_\1_", e)
        out.append(e)
    if in_code and code:
        out.append(f"```{lang}\n" + "\n".join(code) + "\n```")
    return "\n".join(out)


async def send_text(app: Application, chat_id: int, text: str):
    try:
        await app.bot.send_message(chat_id, format_ai_response(text), parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await app.bot.send_message(chat_id, text)


async def send_formatted(update: Update, text: str):
    try:
        await update.message.reply_text(format_ai_response(text), parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(text)


# ── Command handlers ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    registry.register(str(user.id), update.effective_chat.id, user.first_name or "")
    schedule_user_jobs(context.application, str(user.id))
    text = (
        f"👋 *Hey {escape_md(user.first_name or 'there')}\\!*\n\n"
        "I'm your *proactive* personal assistant\\. I quietly track what matters — habits, tasks, "
        "health, mood, anything measurable — and I reach out on my own to keep you organized\\.\n\n"
        "*I'll send you:*\n"
        "• ☀️ a morning briefing\n"
        "• 🌙 an evening review with insights\n"
        "• 💡 the occasional nudge \\(streaks, deadlines\\)\n\n"
        "*Just talk to me naturally:*\n"
        "• _\"Ran 5k this morning, felt great\"_\n"
        "• _\"Remind me to call mom at 6pm\"_\n"
        "• _\"I need to submit the report by Friday\"_\n\n"
        "*Commands:* /track /insights /tasks /reminders /memories /pause /resume /forget /help"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*How I work:*\n\n"
        "*🧠 I track everything* — tell me anything and I file it: stable facts, measurable data "
        "\\(runs, weight, sleep, money, study hours…\\), tasks with deadlines, recurring habits, and mood\\.\n\n"
        "*📈 I find patterns* — I watch trends over time and surface insights, not just store facts\\.\n\n"
        "*🔔 I'm proactive* — morning briefing, evening review, and rate\\-limited nudges for streaks "
        "and deadlines\\. Use /pause anytime\\.\n\n"
        "*Commands:*\n"
        "• /track — dashboard of what I'm tracking\n"
        "• /insights — insights \\+ suggestions right now\n"
        "• /tasks — your open tasks\n"
        "• /reminders — pending reminders\n"
        "• /memories — stable facts I've stored\n"
        "• /pause /resume — proactive messages\n"
        "• /forget — wipe everything"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = str(user.id)

    first_time = registry.get(user_id) is None
    registry.register(user_id, chat_id, user.first_name or "")
    if first_time:
        schedule_user_jobs(context.application, user_id)

    history = context.user_data.get("history", [])
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await chat(user_id, update.message.text, history, context.application, chat_id)

    history += [{"role": "user", "content": update.message.text}, {"role": "assistant", "content": reply}]
    context.user_data["history"] = history[-20:]
    await send_formatted(update, reply)


async def track_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store = get_store(user_id)

    lines = ["📊 *What I'm tracking*\n"]
    habits = store.active_habits()
    if habits:
        lines.append("*🔥 Habits*")
        lines += [f"• {escape_md(h['name'])}: day {h.get('streak', 0)} \\(best {h.get('best_streak', 0)}\\)" for h in habits]
        lines.append("")
    open_t = store.open_tasks()
    if open_t:
        lines.append("*✅ Open tasks*")
        for t in open_t:
            due = f" — _{escape_md(t['due'][:16])}_" if t.get("due") else ""
            lines.append(f"• {escape_md(t['task'])}{due}")
        lines.append("")
    trends = store.trends()
    if trends:
        lines.append("*📈 Trends*")
        lines += [f"• {escape_md(t)}" for t in trends]
        lines.append("")
    mood = store.recent_mood(7)
    if mood:
        avg = sum(m["mood"] for m in mood) / len(mood)
        lines.append(f"*🙂 Mood \\(7d\\)*: {avg:.1f}/10 over {len(mood)} entries\n")

    if len(lines) == 1:
        lines.append("_Nothing yet — just start telling me about your day\\._")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def insights_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    store = get_store(user_id)
    if not store.facts() and not store.recent_log(30) and not store.open_tasks():
        await update.message.reply_text("I don't have enough to go on yet — tell me about your day first 🙂")
        return
    text = build_digest(store, registry.tz(user_id), "ondemand")
    await send_formatted(update, f"💡 *Insights*\n\n{text}")


async def view_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = get_store(str(update.effective_user.id))
    open_t = store.open_tasks()
    if not open_t:
        await update.message.reply_text("📭 *No open tasks\\!*", parse_mode=ParseMode.MARKDOWN_V2)
        return
    lines = [f"✅ *Open Tasks* \\({len(open_t)}\\)\n"]
    for i, t in enumerate(open_t, 1):
        due = f" — _{escape_md(t['due'][:16])}_" if t.get("due") else ""
        lines.append(f"{i}\\. {escape_md(t['task'])}{due}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pending = reminder_store.get_all_for_chat(chat_id)
    if not pending:
        await update.message.reply_text("📭 *No pending reminders\\!*", parse_mode=ParseMode.MARKDOWN_V2)
        return
    tz = registry.tz(str(update.effective_user.id))
    lines = [f"⏰ *Pending Reminders* \\({len(pending)}\\)\n"]
    for i, r in enumerate(pending, 1):
        ts = r["fire_at_dt"].astimezone(tz).strftime("%a %d %b, %H:%M")
        lines.append(f"{i}\\. {escape_md(r['task'])}\n    _🕐 {escape_md(ts)}_")
    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def view_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    facts = get_store(str(update.effective_user.id)).facts()
    if not facts:
        await update.message.reply_text("📭 *No memories yet\\!*", parse_mode=ParseMode.MARKDOWN_V2)
        return
    lines = [f"📚 *What I remember* \\({len(facts)}\\)\n"] + [f"{i}\\. {escape_md(f)}" for i, f in enumerate(facts, 1)]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def pause_proactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registry.set(str(update.effective_user.id), paused=True)
    await update.message.reply_text("🔕 Proactive messages *paused*\\. Use /resume to turn them back on\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def resume_proactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registry.set(str(update.effective_user.id), paused=False)
    await update.message.reply_text("🔔 Proactive messages *resumed*\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def forget_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_store(str(update.effective_user.id)).forget_all()
    context.user_data.clear()
    await update.message.reply_text("🗑️ *Everything cleared\\.* Fresh start\\.", parse_mode=ParseMode.MARKDOWN_V2)


# ── Bot setup ────────────────────────────────────────────────────────────────────
async def post_init(application: Application):
    # Restore reminders
    pending = reminder_store.get_pending()
    if pending:
        print(f"[reminders] restoring {len(pending)}")
    for r in pending:
        schedule_reminder(application, r["id"], r["chat_id"], r["task"], r["fire_at_dt"])

    # Schedule per-user digests for everyone we already know
    known = registry.all()
    if known:
        print(f"[proactive] scheduling digests for {len(known)} user(s)")
    for user_id in known:
        schedule_user_jobs(application, user_id)

    # Global hourly nudge sweep
    application.job_queue.run_repeating(nudge_sweep, interval=3600, first=60, name="nudge_sweep")

    commands = [
        BotCommand("start", "Welcome & setup"),
        BotCommand("track", "Dashboard of what I track"),
        BotCommand("insights", "Insights & suggestions now"),
        BotCommand("tasks", "Your open tasks"),
        BotCommand("reminders", "Pending reminders"),
        BotCommand("memories", "Facts I remember"),
        BotCommand("pause", "Pause proactive messages"),
        BotCommand("resume", "Resume proactive messages"),
        BotCommand("forget", "Wipe everything"),
        BotCommand("help", "How I work"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("track", track_dashboard))
    application.add_handler(CommandHandler("insights", insights_now))
    application.add_handler(CommandHandler("tasks", view_tasks))
    application.add_handler(CommandHandler("reminders", view_reminders))
    application.add_handler(CommandHandler("memories", view_memories))
    application.add_handler(CommandHandler("pause", pause_proactive))
    application.add_handler(CommandHandler("resume", resume_proactive))
    application.add_handler(CommandHandler("forget", forget_memories))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"PA running. model={brain.MODEL} proxy={brain.ANTHROPIC_BASE_URL}")
    print("Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()
