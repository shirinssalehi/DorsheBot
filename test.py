import os
import re
import requests
from bs4 import BeautifulSoup
from math import ceil

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8504791736:AAG4K-LBCNaODtt-7ljEQ8lJtgMZoZj7Do0")

# Without @
CHANNEL_USERNAME = "dorshegoldgallery"

TGJU_URL = "https://www.tgju.org/profile/geram18"

# ============================================


def fetch_gold_price():
    """
    Fetch current 'نرخ فعلی' for طلای ۱۸ عیار / ۷۵۰ from tgju.org.
    Returns price in ریال as integer, or None on error.
    """
    try:
        resp = requests.get(TGJU_URL, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print("Error fetching tgju:", e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Try to find 'نرخ فعلی 118,343,000'
    m = re.search(r"نرخ فعلی[: ]+([\d,]+)", text)
    if not m:
        # fallback: 'در حال حاضر قیمت هر طلای 18 عیار / 750 118,343,000 ریال'
        m = re.search(r"در حال حاضر قیمت هر طلای.*?([\d,]+)\s*ریال", text)
    if not m:
        return None

    price_rial = int(m.group(1).replace(",", ""))
    return price_rial


def parse_caption_values(caption: str):
    """
    Parse وزن, اجرت, and سود from caption text.
    Returns (weight, tip_pct, profit_pct). tip and profit default to 0 if not found.
    """
    w_match = re.search(r"وزن\s*[:：]?\s*([\d.]+)", caption)
    t_match = re.search(r"(اجرت|tip)\s*[:：]?\s*([\d.]+)", caption, re.IGNORECASE)
    p_match = re.search(r"(سود|profit)\s*[:：]?\s*([\d.]+)", caption, re.IGNORECASE)

    weight = float(w_match.group(1)) if w_match else None
    tip_pct = float(t_match.group(2)) if t_match else 0.0
    profit_pct = float(p_match.group(2)) if p_match else 0.0

    return weight, tip_pct, profit_pct


def calculate_price(weight: float, tip_pct: float, profit_pct: float, gold_price_rial: int):
    """
    Formula: base = weight * gold_price
             with_profit = base * (1 + profit_pct/100)
             final = with_profit * (1 + tip_pct/100)
    Returns (price_rial, price_toman).
    """
    base = weight * gold_price_rial
    with_profit = base * (1 + profit_pct / 100)
    total = with_profit * (1 + tip_pct / 100)
    price_rial = int(total)
    price_toman = int(price_rial / 10)
    return price_rial, price_toman


# ============= TELEGRAM HANDLERS =============

async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered on every post in any channel where the bot is admin.
    If the channel is @dorshegoldgallery, we parse caption and
    attach the 'محاسبه قیمت آنلاین' button.
    """
    message = update.channel_post
    if not message:
        return

    # Only our channel
    if (message.chat.username or "").lower() != CHANNEL_USERNAME.lower():
        return

    caption = message.caption or message.text or ""
    weight, tip_pct, profit_pct = parse_caption_values(caption)

    if weight is None:
        print("No وزن found in caption; skipping button.")
        return

    # Pack numbers into callback_data
    callback_data = f"calc:{weight}:{tip_pct:.3f}:{profit_pct:.3f}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("محاسبه قیمت آنلاین 💰", callback_data=callback_data)]
    ])

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reply_markup=keyboard,
        )
        print(f"Button added to message {message.message_id}")
    except Exception as e:
        print("Error adding button:", e)


async def on_calc_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles presses on 'محاسبه قیمت آنلاین' button.
    Shows result in a popup (alert), not as a new message in the channel.
    """
    query = update.callback_query

    data = query.data or ""
    try:
        _, w_str, t_str, p_str = data.split(":")
        weight = float(w_str)
        tip_pct = float(t_str)
        profit_pct = float(p_str)
    except Exception:
        await query.answer("❗ خطا در خواندن اطلاعات وزن، اجرت و سود.", show_alert=True)
        return

    gold_price_rial = fetch_gold_price()
    if gold_price_rial is None:
        await query.answer("❗ نتوانستم قیمت لحظه‌ای طلا را از سایت بخوانم.", show_alert=True)
        return

    price_rial, price_toman = calculate_price(weight, tip_pct, profit_pct, gold_price_rial)

    # Keep it short – alerts have a length limit and no formatting
    text = (
        f"💰 محاسبه قیمت\n"
        # f"وزن: {weight} / اجرت: {tip}\n"
        f"هر گرم(tgju): {gold_price_rial//10:,} تومان\n"
        f"قیمت نهایی: {price_toman:,} تومان"
    )

    await query.answer(text, show_alert=True)



# ================ MAIN =======================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handler for channel posts
    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL,
            on_channel_post,
        )
    )

    # Handler for button clicks
    app.add_handler(CallbackQueryHandler(on_calc_button, pattern=r"^calc:"))

    print("Bot is running...")
    app.run_polling()



if __name__ == "__main__":
    main()
