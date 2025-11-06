import telebot
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import threading
import time
from telebot import types
import weather_app

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================
# In-memory user storage
# ==========================
# user_id -> {"city": str|None, "lat": float|None, "lon": float|None,
#             "notify": bool, "last_state": {"temp": float|None, "rain_alerted": bool}}
USERS = {}

# message_id of last inline forecast sent per user to keep UI as one message
# user_id -> message_id
LAST_INLINE_FORECAST_MSG = {}


def get_user(user_id: int) -> dict:
    if user_id not in USERS:
        USERS[user_id] = {
            "city": None,
            "lat": None,
            "lon": None,
            "notify": False,
            "last_state": {"temp": None, "rain_alerted": False}
        }
    return USERS[user_id]


def main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(
        types.KeyboardButton("🌆 Погода по городу"),
        types.KeyboardButton("📍 Отправить геолокацию", request_location=True)
    )
    kb.row(
        types.KeyboardButton("🗓 Прогноз на 5 дней"),
        types.KeyboardButton("🔔 Уведомления")
    )
    kb.row(
        types.KeyboardButton("⚖️ Сравнить города"),
        types.KeyboardButton("🧭 Расширенные данные")
    )
    return kb


@bot.message_handler(commands=["start", "help"])
def on_start(message: types.Message):
    user = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Привет! Я погодный бот. Выберите действие:",
        reply_markup=main_menu_keyboard()
    )


# ==========================
# 1) Current weather by city
# ==========================

@bot.message_handler(func=lambda m: m.text == "🌆 Погода по городу")
def ask_city_weather(message: types.Message):
    bot.send_message(message.chat.id, "Введите название города (например: Москва):")
    bot.register_next_step_handler(message, handle_city_weather_input)


def format_current_weather(data: dict) -> str:
    if not data:
        return "Не удалось получить погоду. Попробуйте позже."
    name = data.get("name") or ""
    main = data.get("main", {})
    wind = data.get("wind", {})
    weather = (data.get("weather") or [{}])[0]
    sys = data.get("sys", {})
    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    pres = main.get("pressure")
    wind_spd = wind.get("speed")
    clouds = (data.get("clouds") or {}).get("all")
    sunrise = sys.get("sunrise")
    sunset = sys.get("sunset")
    sunrise_str = datetime.fromtimestamp(sunrise).strftime("%H:%M") if sunrise else "—"
    sunset_str = datetime.fromtimestamp(sunset).strftime("%H:%M") if sunset else "—"
    desc = weather.get("description", "")
    return (
        f"🏙 Город: {name}\n"
        f"☁️ Погодa: {desc}\n"
        f"🌡 Температура: {temp}°C (ощущается как {feels}°C)\n"
        f"💧 Влажность: {hum}%\n"
        f"🌬 Ветер: {wind_spd} м/с\n"
        f"☁️ Облачность: {clouds}%\n"
        f"🔽 Давление: {pres} гПа\n"
        f"🌅 Восход: {sunrise_str}  🌇 Закат: {sunset_str}"
    )


def handle_city_weather_input(message: types.Message):
    city = (message.text or "").strip()
    if not city:
        bot.send_message(message.chat.id, "Пустое название города. Отменено.")
        return
    data = weather_app.get_current_weather(city=city)
    if data and "coord" in data:
        user = get_user(message.from_user.id)
        user["city"] = city
        user["lat"] = data["coord"].get("lat")
        user["lon"] = data["coord"].get("lon")
    bot.send_message(message.chat.id, format_current_weather(data), reply_markup=main_menu_keyboard())


# =====================================
# 2) Forecast (5 days) with inline UI
# =====================================

@bot.message_handler(func=lambda m: m.text == "🗓 Прогноз на 5 дней")
def show_forecast_days(message: types.Message):
    user = get_user(message.from_user.id)
    if not user.get("lat") or not user.get("lon"):
        bot.send_message(message.chat.id, "Сначала отправьте геолокацию или запросите погоду по городу, чтобы сохранить место.")
        return
    send_forecast_days_inline(message.chat.id, message.from_user.id, user["lat"], user["lon"]) 


def group_forecast_by_day(forecast: dict):
    """Return dict date_str -> list of 3h entries"""
    days = {}
    for item in (forecast.get("list") or []):
        ts = item.get("dt")
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        days.setdefault(day, []).append(item)
    return days


def day_summary(entries: list) -> str:
    temps = [e.get("main", {}).get("temp") for e in entries if e.get("main")]
    desc = ((entries[0].get("weather") or [{}])[0]).get("description", "") if entries else ""
    if temps:
        return f"{min(temps):.0f}…{max(temps):.0f}°C, {desc}"
    return desc


def build_days_keyboard(days_keys: list) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for day in days_keys:
        label = datetime.strptime(day, "%Y-%m-%d").strftime("%a %d.%m")
        kb.add(types.InlineKeyboardButton(text=label, callback_data=f"day:{day}"))
    return kb


def build_day_details_keyboard(day: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back:days"))
    return kb


def format_day_details(day: str, entries: list) -> str:
    lines = [f"📅 {datetime.strptime(day, '%Y-%m-%d').strftime('%A %d.%m')}"]
    for e in entries:
        t = datetime.fromtimestamp(e.get("dt")).strftime("%H:%M")
        main = e.get("main", {})
        w = (e.get("weather") or [{}])[0]
        wind = e.get("wind", {})
        lines.append(
            f"{t}  {w.get('description','')}  {main.get('temp','?')}°C  "
            f"💧{main.get('humidity','?')}%  🌬{wind.get('speed','?')} м/с"
        )
    return "\n".join(lines)


def send_forecast_days_inline(chat_id: int, user_id: int, lat: float, lon: float):
    data = weather_app.get_hourly_weather(lat, lon)
    if not data:
        bot.send_message(chat_id, "Не удалось получить прогноз.")
        return
    days = group_forecast_by_day(data)
    days_keys = sorted(days.keys())[:5]
    text = "Выберите день для подробностей:\n" + "\n".join(
        [f"• {datetime.strptime(d, '%Y-%m-%d').strftime('%a %d.%m')}: {day_summary(days[d])}" for d in days_keys]
    )
    msg = bot.send_message(chat_id, text, reply_markup=build_days_keyboard(days_keys))
    LAST_INLINE_FORECAST_MSG[user_id] = msg.message_id
    # cache forecast per user for callbacks
    USERS[user_id].setdefault("forecast_cache", {})
    USERS[user_id]["forecast_cache"] = {"data": data, "days": days}


@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("day:") or c.data == "back:days"))
def on_forecast_callback(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    cache = user.get("forecast_cache") or {}
    data = cache.get("data")
    days = cache.get("days") or {}
    if call.data.startswith("day:"):
        day = call.data.split(":", 1)[1]
        text = format_day_details(day, days.get(day, []))
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=build_day_details_keyboard(day)
        )
    else:
        # back to days list
        days_keys = sorted(days.keys())[:5]
        text = "Выберите день для подробностей:\n" + "\n".join(
            [f"• {datetime.strptime(d, '%Y-%m-%d').strftime('%a %d.%m')}: {day_summary(days[d])}" for d in days_keys]
        )
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=build_days_keyboard(days_keys)
        )
    bot.answer_callback_query(call.id)


# =============================================
# 3) Geolocation: save and show current weather
# =============================================

@bot.message_handler(content_types=["location"])
def on_location(message: types.Message):
    if not message.location:
        return
    user = get_user(message.from_user.id)
    user["lat"] = message.location.latitude
    user["lon"] = message.location.longitude
    data = weather_app.get_current_weather(latitude=user["lat"], longitude=user["lon"])
    bot.send_message(message.chat.id, "Местоположение сохранено. Текущая погода:\n\n" + format_current_weather(data), reply_markup=main_menu_keyboard())


@bot.message_handler(func=lambda m: m.text == "📍 Отправить геолокацию")
def ask_geo(message: types.Message):
    bot.send_message(message.chat.id, "Нажмите кнопку '📍 Отправить геолокацию' ниже, чтобы поделиться местоположением.")


# =============================================
# 4) Notifications every 2 hours
# =============================================

@bot.message_handler(func=lambda m: m.text == "🔔 Уведомления")
def toggle_notifications(message: types.Message):
    user = get_user(message.from_user.id)
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(text="Включить", callback_data="notif:on"),
        types.InlineKeyboardButton(text="Выключить", callback_data="notif:off")
    )
    status = "включены" if user.get("notify") else "выключены"
    bot.send_message(message.chat.id, f"Уведомления сейчас {status}. Включить или выключить?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("notif:"))
def on_notif_toggle(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    action = call.data.split(":", 1)[1]
    if action == "on":
        user["notify"] = True
        bot.answer_callback_query(call.id, "Уведомления включены")
    else:
        user["notify"] = False
        bot.answer_callback_query(call.id, "Уведомления выключены")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass


def scheduler_loop():
    while True:
        try:
            for user_id, info in list(USERS.items()):
                if not info.get("notify"):
                    continue
                lat, lon = info.get("lat"), info.get("lon")
                if not lat or not lon:
                    continue
                # current weather
                curr = weather_app.get_current_weather(latitude=lat, longitude=lon)
                if curr:
                    temp = (curr.get("main") or {}).get("temp")
                    last_temp = info.get("last_state", {}).get("temp")
                    if last_temp is None or (isinstance(temp, (int, float)) and isinstance(last_temp, (int, float)) and abs(temp - last_temp) >= 2):
                        try:
                            bot.send_message(user_id, f"ℹ️ Обновление погоды: сейчас {temp}°C")
                        except Exception:
                            pass
                        info["last_state"]["temp"] = temp

                # rain alert for next 24h
                fc = weather_app.get_hourly_weather(lat, lon)
                rain_expected = False
                if fc and fc.get("list"):
                    now_ts = int(time.time())
                    for e in fc["list"]:
                        if e.get("dt", 0) > now_ts + 24*3600:
                            break
                        weather_desc = ((e.get("weather") or [{}])[0]).get("main", "").lower()
                        if "rain" in weather_desc:
                            rain_expected = True
                            break
                if rain_expected and not info["last_state"].get("rain_alerted"):
                    try:
                        bot.send_message(user_id, "☔ Ожидается дождь в течение суток. Возьмите зонт!")
                    except Exception:
                        pass
                    info["last_state"]["rain_alerted"] = True
                if not rain_expected:
                    info["last_state"]["rain_alerted"] = False
        except Exception:
            pass
        time.sleep(2 * 60 * 60)


# =============================================
# 5) Compare two cities
# =============================================

@bot.message_handler(func=lambda m: m.text == "⚖️ Сравнить города")
def ask_compare(message: types.Message):
    bot.send_message(message.chat.id, "Введите два города через запятую (например: Москва, Санкт-Петербург):")
    bot.register_next_step_handler(message, handle_compare_input)


def handle_compare_input(message: types.Message):
    raw = (message.text or "").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 2:
        bot.send_message(message.chat.id, "Нужно указать ровно два города через запятую.")
        return
    c1, c2 = parts
    w1 = weather_app.get_current_weather(city=c1)
    w2 = weather_app.get_current_weather(city=c2)
    def city_row(name, data):
        temp = ((data or {}).get("main") or {}).get("temp", "—")
        hum = ((data or {}).get("main") or {}).get("humidity", "—")
        wind = ((data or {}).get("wind") or {}).get("speed", "—")
        return f"{name:<16} {str(temp):>6}°C   {str(hum):>4}%   {str(wind):>4} м/с"
    header = f"{'Город':<16} {'Темп.':>6}   {'Влаж.':>4}   {'Ветер':>4}"
    txt = "\n".join([header, city_row(c1, w1), city_row(c2, w2)])
    bot.send_message(message.chat.id, f"``\n{txt}\n```", parse_mode="Markdown")


# =============================================
# 6) Advanced data (city or geo)
# =============================================

@bot.message_handler(func=lambda m: m.text == "🧭 Расширенные данные")
def ask_advanced(message: types.Message):
    bot.send_message(message.chat.id, "Введите город ИЛИ отправьте геолокацию заранее, и я покажу расширенные данные.")
    bot.register_next_step_handler(message, handle_advanced_input)


def handle_advanced_input(message: types.Message):
    user = get_user(message.from_user.id)
    text = (message.text or "").strip()
    data = None
    lat = lon = None
    if text:
        data = weather_app.get_current_weather(city=text)
        if data and "coord" in data:
            lat = data["coord"].get("lat")
            lon = data["coord"].get("lon")
    elif user.get("lat") and user.get("lon"):
        lat, lon = user["lat"], user["lon"]
        data = weather_app.get_current_weather(latitude=lat, longitude=lon)
    else:
        bot.send_message(message.chat.id, "Нет данных: введите город или отправьте геолокацию.")
        return

    if not data:
        bot.send_message(message.chat.id, "Не удалось получить данные.")
        return

    # Air pollution analysis
    pollution_txt = "Данных нет"
    if lat and lon:
        ap = weather_app.get_air_pollution(lat, lon)
        analysis = weather_app.analyze_air_pollution(ap) if ap else None
        if analysis and "overall_status" in analysis:
            pollution_txt = f"{analysis['overall_status']} (индекс {analysis['overall_index']})"

    main = data.get("main", {})
    wind = data.get("wind", {})
    clouds = (data.get("clouds") or {}).get("all")
    sys = data.get("sys", {})
    sunrise = sys.get("sunrise")
    sunset = sys.get("sunset")
    sunrise_str = datetime.fromtimestamp(sunrise).strftime("%H:%M") if sunrise else "—"
    sunset_str = datetime.fromtimestamp(sunset).strftime("%H:%M") if sunset else "—"

    uv_txt = "нет данных"
    text_out = (
        f"{format_current_weather(data)}\n\n"
        f"🧪 Качество воздуха: {pollution_txt}\n"
        f"🔆 УФ-индекс: {uv_txt}\n"
        f"Дополнительно: давление {main.get('pressure','?')} гПа, облачность {clouds}%\n"
        f"Солнце: восход {sunrise_str}, закат {sunset_str}"
    )
    bot.send_message(message.chat.id, text_out, reply_markup=main_menu_keyboard())


# ================
# Fallback handler
# ================

@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message: types.Message):
    bot.send_message(message.chat.id, "Выберите действие из меню ниже.", reply_markup=main_menu_keyboard())


def run_bot():
    # Start scheduler thread
    th = threading.Thread(target=scheduler_loop, daemon=True)
    th.start()
    bot.infinity_polling()


if __name__ == "__main__":
    run_bot()

