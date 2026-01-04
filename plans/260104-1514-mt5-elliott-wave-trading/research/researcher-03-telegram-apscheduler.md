# Telegram Bot & APScheduler Research

**Date**: 2026-01-04 | **Focus**: Notification system and scheduling

---

## 1. Telegram Bot Setup (python-telegram-bot v20+)

**Installation**:
```bash
pip install python-telegram-bot[job-queue]
```

**Bot Creation**:
1. Message @BotFather on Telegram
2. Send `/newbot` and follow prompts
3. Get bot token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. Get chat ID by messaging bot and checking `/getUpdates`

---

## 2. Basic Bot Structure

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

async def start(update: Update, context):
    await update.message.reply_text("EW Trading Bot Active")

async def send_signal(bot, chat_id, signal_data):
    """Send trading signal with inline buttons"""

    text = f"""
🔔 *XAUUSD Signal*

📊 *Action*: {signal_data['action']}
💰 *Entry*: {signal_data['entry_price']}
🛑 *SL*: {signal_data['stop_loss']}
🎯 *TP1*: {signal_data['tp1']} (50%)
🎯 *TP2*: {signal_data['tp2']} (30%)
🎯 *TP3*: {signal_data['tp3']} (20%)

📈 *R:R*: {signal_data['risk_reward']}
🎯 *Confidence*: {signal_data['confidence']}%

_Wave Analysis_: {signal_data['wave_description']}
"""

    keyboard = [
        [
            InlineKeyboardButton("✅ Execute", callback_data="execute"),
            InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
        ],
        [
            InlineKeyboardButton("✏️ Modify", callback_data="modify"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
```

---

## 3. Callback Handling

```python
async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "execute":
        # Get signal from context
        signal = context.user_data.get('pending_signal')
        if signal:
            # Execute trade via MT5
            result = execute_trade(signal)
            await query.edit_message_text(f"✅ Trade executed: {result}")

    elif query.data == "skip":
        await query.edit_message_text("⏭️ Signal skipped")

    elif query.data == "modify":
        await query.edit_message_text(
            "Enter modifications (format: sl=3310 tp1=3380):",
        )
        context.user_data['awaiting_modification'] = True
```

---

## 4. APScheduler Integration

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

async def m15_analysis_job():
    """Run every M15 close"""
    # 1. Export CSV from MT5
    # 2. Call Claude API
    # 3. Parse signal
    # 4. Send to Telegram if valid
    pass

def setup_scheduler():
    # Run at M15 close times: :00, :15, :30, :45
    scheduler.add_job(
        m15_analysis_job,
        CronTrigger(minute='0,15,30,45'),
        id='m15_analysis',
        replace_existing=True
    )
    scheduler.start()
```

---

## 5. Confirmation Timeout

```python
import asyncio

async def send_signal_with_timeout(bot, chat_id, signal, timeout=300):
    """Send signal and wait for confirmation with timeout"""

    # Send signal message
    msg = await send_signal(bot, chat_id, signal)

    # Store pending signal
    pending_signals[msg.message_id] = {
        'signal': signal,
        'expires': time.time() + timeout
    }

    # Schedule expiration
    asyncio.create_task(expire_signal(bot, chat_id, msg.message_id, timeout))

async def expire_signal(bot, chat_id, message_id, timeout):
    await asyncio.sleep(timeout)
    if message_id in pending_signals:
        del pending_signals[message_id]
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⏰ Signal expired (5 min timeout)"
        )
```

---

## 6. Complete Application Setup

```python
import asyncio
from telegram.ext import Application

async def main():
    # Create application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Setup scheduler
    setup_scheduler()

    # Start bot
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Keep running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. Error Handling

```python
from telegram.error import TelegramError, NetworkError

async def safe_send_message(bot, chat_id, text, retries=3):
    for attempt in range(retries):
        try:
            return await bot.send_message(chat_id=chat_id, text=text)
        except NetworkError:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            continue
        except TelegramError as e:
            logging.error(f"Telegram error: {e}")
            raise
    raise Exception("Failed after retries")
```

---

## Key Findings

| Aspect | Status | Notes |
|--------|--------|-------|
| **Library** | ✅ | `python-telegram-bot` v20+ |
| **Inline Buttons** | ✅ | `InlineKeyboardMarkup` |
| **Callbacks** | ✅ | `CallbackQueryHandler` |
| **Scheduling** | ✅ | APScheduler with cron triggers |
| **Timeout** | ✅ | asyncio-based expiration |
| **Error Handling** | ✅ | Retry patterns |

---

## Environment Variables Needed

```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
TELEGRAM_CHAT_ID=987654321
```

---

## Unresolved Questions

1. Multiple users vs single user design?
2. Message rate limits (30 msg/sec to same chat)
3. Webhook vs polling for production?
