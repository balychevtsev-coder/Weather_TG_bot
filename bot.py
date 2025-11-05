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

# Хранение данных пользователей
user_data = {}
user_subscriptions = {}

# Загрузка данных из файла
def load_user_data():
    global user_data, user_subscriptions
    try:
        with open("user_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            user_data = data.get("locations", {})
            user_subscriptions = data.get("subscriptions", {})
    except FileNotFoundError:
        user_data = {}
        user_subscriptions = {}

# Сохранение данных в файл
def save_user_data():
    with open("user_data.json", "w", encoding="utf-8") as f:
        json.dump({
            "locations": user_data,
            "subscriptions": user_subscriptions
        }, f, ensure_ascii=False, indent=2)

# Инициализация
load_user_data()

# Форматирование погоды
def format_current_weather(weather_data):
    if not weather_data:
        return "❌ Не удалось получить данные о погоде"
    
    main = weather_data.get("main", {})
    weather = weather_data.get("weather", [{}])[0]
    wind = weather_data.get("wind", {})
    sys_data = weather_data.get("sys", {})
    
    city = weather_data.get("name", "Неизвестно")
    temp = main.get("temp", 0)
    feels_like = main.get("feels_like", 0)
    humidity = main.get("humidity", 0)
    pressure = main.get("pressure", 0)
    description = weather.get("description", "Нет данных")
    wind_speed = wind.get("speed", 0)
    wind_deg = wind.get("deg", 0)
    cloudiness = weather_data.get("clouds", {}).get("all", 0)
    
    # Восход и закат
    sunrise = datetime.fromtimestamp(sys_data.get("sunrise", 0))
    sunset = datetime.fromtimestamp(sys_data.get("sunset", 0))
    
    text = f"🌤️ <b>Погода в {city}</b>\n\n"
    text += f"🌡️ Температура: {temp}°C\n"
    text += f"🤔 Ощущается как: {feels_like}°C\n"
    text += f"☁️ {description.capitalize()}\n"
    text += f"💧 Влажность: {humidity}%\n"
    text += f"🌬️ Ветер: {wind_speed} м/с"
    if wind_deg:
        directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        direction = directions[wind_deg // 45]
        text += f" ({direction})\n"
    else:
        text += "\n"
    text += f"☁️ Облачность: {cloudiness}%\n"
    text += f"📊 Давление: {pressure} гПа\n"
    text += f"🌅 Восход: {sunrise.strftime('%H:%M')}\n"
    text += f"🌇 Закат: {sunset.strftime('%H:%M')}\n"
    
    return text

# Форматирование расширенных данных
def format_extended_weather(weather_data, air_pollution_data=None):
    if not weather_data:
        return "❌ Не удалось получить данные о погоде"
    
    text = format_current_weather(weather_data)
    
    # Добавляем данные о загрязнении воздуха
    if air_pollution_data:
        analysis = weather_app.analyze_air_pollution(air_pollution_data)
        if "error" not in analysis:
            text += f"\n🌍 <b>Качество воздуха:</b>\n"
            text += f"Статус: {analysis['overall_status']} (Индекс: {analysis['overall_index']})\n"
            
            pollutants = analysis.get("pollutants_data", {})
            pollutant_names = {
                "so2": "SO₂",
                "no2": "NO₂",
                "pm10": "PM₁₀",
                "pm2_5": "PM₂.₅",
                "o3": "O₃",
                "co": "CO"
            }
            
            for key, name in pollutant_names.items():
                if key in pollutants:
                    conc = pollutants[key]
                    idx = analysis.get("pollutant_indices", {}).get(key, 1)
                    text += f"{name}: {conc:.2f} µg/m³ (Индекс: {idx})\n"
    
    return text

# Форматирование прогноза на день
def format_day_forecast(forecast_data, date_str):
    # Форматируем дату для отображения
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_names_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_name = day_names_ru[dt.weekday()]
        date_display = dt.strftime(f"%d.%m.%Y ({day_name})")
    except:
        date_display = date_str
    
    text = f"📅 <b>{date_display}</b>\n\n"
    
    # Группируем по дням
    day_data = {}
    for item in forecast_data.get("list", []):
        dt = datetime.fromtimestamp(item.get("dt", 0))
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in day_data:
            day_data[day_key] = []
        day_data[day_key].append(item)
    
    # Находим нужный день
    target_date = None
    for key in sorted(day_data.keys()):
        if key >= date_str:
            target_date = key
            break
    
    if not target_date:
        return "❌ Данные для этого дня не найдены"
    
    items = day_data[target_date]
    
    # Средние значения за день
    temps = [item["main"]["temp"] for item in items]
    max_temp = max(temps)
    min_temp = min(temps)
    avg_temp = sum(temps) / len(temps)
    
    # Погодные условия (берем самое частое)
    conditions = {}
    for item in items:
        desc = item["weather"][0]["description"]
        conditions[desc] = conditions.get(desc, 0) + 1
    main_condition = max(conditions, key=conditions.get)
    
    # Влажность и ветер
    humidity = sum([item["main"]["humidity"] for item in items]) / len(items)
    wind_speed = sum([item.get("wind", {}).get("speed", 0) for item in items]) / len(items)
    
    text += f"🌡️ Температура: {min_temp:.1f}°C - {max_temp:.1f}°C\n"
    text += f"📊 Средняя: {avg_temp:.1f}°C\n"
    text += f"☁️ {main_condition.capitalize()}\n"
    text += f"💧 Влажность: {humidity:.0f}%\n"
    text += f"🌬️ Ветер: {wind_speed:.1f} м/с\n"
    text += f"📋 Прогнозов на день: {len(items)}\n"
    
    return text

# Главное меню
def create_main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(types.KeyboardButton("🌤️ Прогноз погоды"))
    keyboard.add(types.KeyboardButton("📅 Прогноз на 5 дней"))
    keyboard.add(types.KeyboardButton("📍 Поиск по геолокации"), types.KeyboardButton("🔔 Уведомления"))
    keyboard.add(types.KeyboardButton("⚖️ Сравнение городов"))
    keyboard.add(types.KeyboardButton("📊 Расширенные данные"))
    return keyboard

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = str(message.from_user.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    
    welcome_text = "👋 Добро пожаловать в бот погоды!\n\n"
    welcome_text += "Выберите одну из функций:\n"
    welcome_text += "🌤️ Прогноз погоды - текущая погода по городу\n"
    welcome_text += "📅 Прогноз на 5 дней - прогноз для сохраненного местоположения\n"
    welcome_text += "📍 Поиск по геолокации - отправьте свою геолокацию\n"
    welcome_text += "🔔 Уведомления - подписка на погодные уведомления\n"
    welcome_text += "⚖️ Сравнение городов - сравнение температуры в двух городах\n"
    welcome_text += "📊 Расширенные данные - полная информация о погоде\n"
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_menu(), parse_mode="HTML")

# Функция 1: Прогноз погоды
@bot.message_handler(func=lambda message: message.text == "🌤️ Прогноз погоды")
def weather_forecast_handler(message):
    bot.send_message(message.chat.id, "Введите название города:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, process_city_weather)

def process_city_weather(message):
    city = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Загружаю данные...")
    
    try:
        weather = weather_app.get_current_weather(city=city)
        if weather:
            text = format_current_weather(weather)
            try:
                sent_msg = bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=create_main_menu())
                print(f"DEBUG: Расширенные данные отправлены успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке расширенных данных: {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    import re
                    text_plain = re.sub(r'<[^>]+>', '', text)
                    bot.send_message(message.chat.id, text_plain, reply_markup=create_main_menu())
                except Exception as e2:
                    bot.send_message(message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Не удалось найти город. Попробуйте еще раз.", reply_markup=create_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

# Функция 2: Прогноз на 5 дней (с сохраненным местоположением)
@bot.message_handler(func=lambda message: message.text == "📅 Прогноз на 5 дней")
def forecast_5days_handler(message):
    print(f"DEBUG: Прогноз на 5 дней вызван пользователем {message.from_user.id}")
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or "latitude" not in user_data[user_id]:
        bot.send_message(message.chat.id, "❌ Сначала сохраните ваше местоположение через функцию '📍 Поиск по геолокации'", reply_markup=create_main_menu())
        return
    
    lat = user_data[user_id]["latitude"]
    lon = user_data[user_id]["longitude"]
    
    bot.send_message(message.chat.id, "⏳ Загружаю прогноз...")
    
    try:
        print(f"DEBUG: Запрос прогноза для lat={lat}, lon={lon}")
        forecast = weather_app.get_hourly_weather(lat, lon)
        print(f"DEBUG: forecast получен: {forecast is not None}")
        if forecast:
            print(f"DEBUG: forecast keys: {forecast.keys() if isinstance(forecast, dict) else 'not dict'}")
            print(f"DEBUG: forecast['list'] exists: {'list' in forecast if isinstance(forecast, dict) else False}")
        
        if forecast and "list" in forecast and len(forecast["list"]) > 0:
            # Группируем по дням
            day_groups = {}
            for item in forecast.get("list", []):
                dt = datetime.fromtimestamp(item.get("dt", 0))
                day_key = dt.strftime("%Y-%m-%d")
                if day_key not in day_groups:
                    day_groups[day_key] = []
                day_groups[day_key].append(item)
            
            if not day_groups:
                bot.send_message(message.chat.id, "❌ Не удалось получить данные прогноза", reply_markup=create_main_menu())
                return
            
            # Создаем inline клавиатуру
            keyboard = types.InlineKeyboardMarkup()
            sorted_days = sorted(day_groups.items())[:5]
            
            if not sorted_days:
                bot.send_message(message.chat.id, "❌ Нет данных для отображения", reply_markup=create_main_menu())
                return
            
            for i, (day_key, items) in enumerate(sorted_days, 1):
                dt = datetime.strptime(day_key, "%Y-%m-%d")
                # Упрощаем названия дней
                day_names_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                day_name_short = day_names_ru[dt.weekday()]
                keyboard.add(types.InlineKeyboardButton(
                    f"{i}. {dt.strftime('%d.%m')} {day_name_short}",
                    callback_data=f"day_{day_key}"
                ))
            
            text = "📅 <b>Прогноз на 5 дней:</b>\nВыберите день для подробной информации:"
            try:
                sent_msg = bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=keyboard)
                print(f"DEBUG: Сообщение отправлено успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке сообщения: {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    text_plain = "📅 Прогноз на 5 дней:\nВыберите день для подробной информации:"
                    bot.send_message(message.chat.id, text_plain, reply_markup=keyboard)
                except Exception as e2:
                    bot.send_message(message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Не удалось получить прогноз. Проверьте наличие API ключа.", reply_markup=create_main_menu())
    except Exception as e:
        import traceback
        error_msg = f"❌ Ошибка: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Логируем полную ошибку
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

# Обработчик callback для дней
@bot.callback_query_handler(func=lambda call: call.data.startswith("day_"))
def day_detail_handler(call):
    user_id = str(call.from_user.id)
    
    if user_id not in user_data or "latitude" not in user_data[user_id]:
        bot.answer_callback_query(call.id, "❌ Местоположение не сохранено")
        return
    
    date_str = call.data.replace("day_", "")
    lat = user_data[user_id]["latitude"]
    lon = user_data[user_id]["longitude"]
    
    try:
        forecast = weather_app.get_hourly_weather(lat, lon)
        if forecast and "list" in forecast and len(forecast["list"]) > 0:
            text = format_day_forecast(forecast, date_str)
            
            if "❌" in text:
                bot.answer_callback_query(call.id, "❌ Данные не найдены")
                return
            
            # Кнопка "Назад"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_days"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка получения данных")
    except Exception as e:
        import traceback
        print(f"Ошибка в day_detail_handler: {traceback.format_exc()}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

# Обработчик возврата к списку дней
@bot.callback_query_handler(func=lambda call: call.data == "back_to_days")
def back_to_days_handler(call):
    user_id = str(call.from_user.id)
    
    if user_id not in user_data or "latitude" not in user_data[user_id]:
        bot.answer_callback_query(call.id, "❌ Местоположение не сохранено")
        return
    
    lat = user_data[user_id]["latitude"]
    lon = user_data[user_id]["longitude"]
    
    try:
        forecast = weather_app.get_hourly_weather(lat, lon)
        if forecast and "list" in forecast and len(forecast["list"]) > 0:
            day_groups = {}
            for item in forecast.get("list", []):
                dt = datetime.fromtimestamp(item.get("dt", 0))
                day_key = dt.strftime("%Y-%m-%d")
                if day_key not in day_groups:
                    day_groups[day_key] = []
                day_groups[day_key].append(item)
            
            if not day_groups:
                bot.answer_callback_query(call.id, "❌ Нет данных")
                return
            
            keyboard = types.InlineKeyboardMarkup()
            sorted_days = sorted(day_groups.items())[:5]
            
            for i, (day_key, items) in enumerate(sorted_days, 1):
                dt = datetime.strptime(day_key, "%Y-%m-%d")
                day_names_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                day_name_short = day_names_ru[dt.weekday()]
                keyboard.add(types.InlineKeyboardButton(
                    f"{i}. {dt.strftime('%d.%m')} {day_name_short}",
                    callback_data=f"day_{day_key}"
                ))
            
            text = "📅 <b>Прогноз на 5 дней:</b>\nВыберите день для подробной информации:"
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка получения данных")
    except Exception as e:
        import traceback
        print(f"Ошибка в back_to_days_handler: {traceback.format_exc()}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

# Функция 3: Поиск по геолокации
@bot.message_handler(func=lambda message: message.text == "📍 Поиск по геолокации")
def location_handler(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(types.KeyboardButton("📍 Отправить местоположение", request_location=True))
    keyboard.add(types.KeyboardButton("◀️ Назад в меню"))
    bot.send_message(message.chat.id, "📍 Отправьте ваше местоположение:", reply_markup=keyboard)

@bot.message_handler(content_types=['location'])
def location_received(message):
    user_id = str(message.from_user.id)
    lat = message.location.latitude
    lon = message.location.longitude
    
    # Сохраняем местоположение
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["latitude"] = lat
    user_data[user_id]["longitude"] = lon
    save_user_data()
    
    bot.send_message(message.chat.id, "⏳ Загружаю данные о погоде...")
    
    try:
        weather = weather_app.get_current_weather(latitude=lat, longitude=lon)
        if weather:
            text = format_current_weather(weather)
            text += f"\n✅ Местоположение сохранено!"
            try:
                sent_msg = bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=create_main_menu())
                print(f"DEBUG: Расширенные данные отправлены успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке расширенных данных: {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    import re
                    text_plain = re.sub(r'<[^>]+>', '', text)
                    bot.send_message(message.chat.id, text_plain, reply_markup=create_main_menu())
                except Exception as e2:
                    bot.send_message(message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Не удалось получить данные о погоде", reply_markup=create_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

# Функция 4: Уведомления
@bot.message_handler(func=lambda message: message.text == "🔔 Уведомления")
def notifications_handler(message):
    user_id = str(message.from_user.id)
    is_subscribed = user_subscriptions.get(user_id, False)
    
    keyboard = types.InlineKeyboardMarkup()
    if is_subscribed:
        keyboard.add(types.InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe"))
        text = "🔔 Вы подписаны на уведомления.\nБот будет проверять погоду каждые 2 часа и уведомлять о дожде."
    else:
        keyboard.add(types.InlineKeyboardButton("✅ Подписаться", callback_data="subscribe"))
        text = "🔔 Подписка на уведомления.\nБот будет проверять погоду каждые 2 часа и уведомлять о дожде."
    
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data in ["subscribe", "unsubscribe"])
def subscription_handler(call):
    user_id = str(call.from_user.id)
    
    if call.data == "subscribe":
        user_subscriptions[user_id] = True
        save_user_data()
        bot.answer_callback_query(call.id, "✅ Подписка активирована")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔔 Вы подписаны на уведомления.\nБот будет проверять погоду каждые 2 часа и уведомлять о дожде.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe")
            )
        )
    else:
        user_subscriptions[user_id] = False
        save_user_data()
        bot.answer_callback_query(call.id, "❌ Подписка отменена")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🔔 Подписка на уведомления.\nБот будет проверять погоду каждые 2 часа и уведомлять о дожде.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("✅ Подписаться", callback_data="subscribe")
            )
        )

# Функция проверки погоды для уведомлений
def check_weather_notifications():
    while True:
        time.sleep(2 * 3600)  # Каждые 2 часа
        
        for user_id, is_subscribed in list(user_subscriptions.items()):
            if not is_subscribed:
                continue
            
            if user_id not in user_data or "latitude" not in user_data[user_id]:
                continue
            
            try:
                lat = user_data[user_id]["latitude"]
                lon = user_data[user_id]["longitude"]
                
                # Получаем текущую погоду и прогноз
                current = weather_app.get_current_weather(latitude=lat, longitude=lon)
                forecast = weather_app.get_hourly_weather(lat, lon)
                
                if current and forecast:
                    # Проверяем текущую погоду на дождь
                    current_weather = current.get("weather", [{}])[0].get("main", "").lower()
                    if "rain" in current_weather or "drizzle" in current_weather:
                        bot.send_message(int(user_id), "🌧️ Внимание! Сейчас идет дождь. Не забудьте зонт!")
                    
                    # Проверяем прогноз на завтра
                    tomorrow = datetime.now() + timedelta(days=1)
                    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
                    
                    for item in forecast.get("list", []):
                        dt = datetime.fromtimestamp(item.get("dt", 0))
                        if dt.strftime("%Y-%m-%d") == tomorrow_str:
                            weather_main = item.get("weather", [{}])[0].get("main", "").lower()
                            if "rain" in weather_main or "drizzle" in weather_main:
                                bot.send_message(int(user_id), f"🌧️ Завтра ({tomorrow.strftime('%d.%m')}) ожидается дождь! Не забудьте зонт!")
                                break
            except Exception as e:
                print(f"Ошибка при проверке уведомлений для {user_id}: {e}")

# Запуск потока для уведомлений
notification_thread = threading.Thread(target=check_weather_notifications, daemon=True)
notification_thread.start()

# Функция 5: Сравнение городов
@bot.message_handler(func=lambda message: message.text == "⚖️ Сравнение городов")
def compare_cities_handler(message):
    bot.send_message(message.chat.id, "Введите первый город:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, process_first_city)

def process_first_city(message):
    city1 = message.text.strip()
    bot.send_message(message.chat.id, "Введите второй город:")
    bot.register_next_step_handler(message, process_second_city, city1)

def process_second_city(message, city1):
    city2 = message.text.strip()
    bot.send_message(message.chat.id, "⏳ Сравниваю города...")
    
    try:
        weather1 = weather_app.get_current_weather(city=city1)
        weather2 = weather_app.get_current_weather(city=city2)
        
        if weather1 and weather2:
            main1 = weather1.get("main", {})
            main2 = weather2.get("main", {})
            
            text = f"⚖️ <b>Сравнение городов</b>\n\n"
            text += f"<b>{city1}</b> vs <b>{city2}</b>\n\n"
            
            # Таблица сравнения (используем моноширинный шрифт)
            text += "<pre>"
            text += "┌─────────────────┬──────────────┬──────────────┐\n"
            text += "│ Параметр        │ {:<12} │ {:<12} │\n".format(city1[:12], city2[:12])
            text += "├─────────────────┼──────────────┼──────────────┤\n"
            
            temp1 = main1.get("temp", 0)
            temp2 = main2.get("temp", 0)
            text += "│ Температура     │ {:<12} │ {:<12} │\n".format(f"{temp1}°C", f"{temp2}°C")
            
            feels1 = main1.get("feels_like", 0)
            feels2 = main2.get("feels_like", 0)
            text += "│ Ощущается как   │ {:<12} │ {:<12} │\n".format(f"{feels1}°C", f"{feels2}°C")
            
            hum1 = main1.get("humidity", 0)
            hum2 = main2.get("humidity", 0)
            text += "│ Влажность       │ {:<12} │ {:<12} │\n".format(f"{hum1}%", f"{hum2}%")
            
            wind1 = weather1.get("wind", {}).get("speed", 0)
            wind2 = weather2.get("wind", {}).get("speed", 0)
            text += "│ Ветер           │ {:<12} │ {:<12} │\n".format(f"{wind1:.1f} м/с", f"{wind2:.1f} м/с")
            
            cloud1 = weather1.get("clouds", {}).get("all", 0)
            cloud2 = weather2.get("clouds", {}).get("all", 0)
            text += "│ Облачность      │ {:<12} │ {:<12} │\n".format(f"{cloud1}%", f"{cloud2}%")
            
            text += "└─────────────────┴──────────────┴──────────────┘"
            text += "</pre>\n"
            
            # Определяем победителя
            if temp1 > temp2:
                text += f"\n🏆 В <b>{city1}</b> теплее на {temp1 - temp2:.1f}°C"
            elif temp2 > temp1:
                text += f"\n🏆 В <b>{city2}</b> теплее на {temp2 - temp1:.1f}°C"
            else:
                text += f"\n🤝 В обоих городах одинаковая температура"
            
            try:
                sent_msg = bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=create_main_menu())
                print(f"DEBUG: Расширенные данные отправлены успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке расширенных данных: {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    import re
                    text_plain = re.sub(r'<[^>]+>', '', text)
                    bot.send_message(message.chat.id, text_plain, reply_markup=create_main_menu())
                except Exception as e2:
                    bot.send_message(message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Не удалось получить данные для одного или обоих городов", reply_markup=create_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

# Функция 6: Расширенные данные
@bot.message_handler(func=lambda message: message.text == "📊 Расширенные данные")
def extended_data_handler(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🏙️ По городу", callback_data="extended_city"))
    keyboard.add(types.InlineKeyboardButton("📍 По геолокации", callback_data="extended_location"))
    bot.send_message(message.chat.id, "Выберите способ получения данных:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "extended_city")
def extended_city_handler(call):
    print(f"DEBUG: extended_city callback получен")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Введите название города:", reply_markup=types.ReplyKeyboardRemove())
    # Создаем временное сообщение для регистрации следующего шага
    msg = bot.send_message(call.message.chat.id, "⏳ Ожидаю ввода города...")
    bot.register_next_step_handler(msg, process_extended_city)

def process_extended_city(message):
    city = message.text.strip()
    
    # Удаляем временное сообщение
    try:
        bot.delete_message(message.chat.id, message.message_id - 1)
    except:
        pass
    
    bot.send_message(message.chat.id, "⏳ Загружаю расширенные данные...")
    
    try:
        weather = weather_app.get_current_weather(city=city)
        print(f"DEBUG: weather = {weather}")  # Отладочный вывод
        if weather:
            try:
                lat, lon = weather_app.get_coordinates(city)
                print(f"DEBUG: lat={lat}, lon={lon}")  # Отладочный вывод
                air_pollution = weather_app.get_air_pollution(lat, lon)
                print(f"DEBUG: air_pollution = {air_pollution}")  # Отладочный вывод
                text = format_extended_weather(weather, air_pollution)
            except Exception as e:
                # Если не удалось получить загрязнение воздуха, показываем обычную погоду
                import traceback
                print(f"Ошибка получения загрязнения воздуха: {e}\n{traceback.format_exc()}")
                text = format_extended_weather(weather, None)
            
            try:
                sent_msg = bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=create_main_menu())
                print(f"DEBUG: Расширенные данные отправлены успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке расширенных данных: {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    import re
                    text_plain = re.sub(r'<[^>]+>', '', text)
                    bot.send_message(message.chat.id, text_plain, reply_markup=create_main_menu())
                except Exception as e2:
                    bot.send_message(message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Не удалось найти город", reply_markup=create_main_menu())
    except Exception as e:
        import traceback
        error_msg = f"❌ Ошибка: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Логируем полную ошибку
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "extended_location")
def extended_location_handler(call):
    print(f"DEBUG: extended_location callback получен")
    bot.answer_callback_query(call.id)
    user_id = str(call.from_user.id)
    
    if user_id not in user_data or "latitude" not in user_data[user_id]:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        keyboard.add(types.KeyboardButton("📍 Отправить местоположение", request_location=True))
        keyboard.add(types.KeyboardButton("◀️ Назад в меню"))
        bot.send_message(call.message.chat.id, "📍 Сначала отправьте ваше местоположение:", reply_markup=keyboard)
        return
    
    lat = user_data[user_id]["latitude"]
    lon = user_data[user_id]["longitude"]
    
    bot.send_message(call.message.chat.id, "⏳ Загружаю расширенные данные...")
    
    try:
        weather = weather_app.get_current_weather(latitude=lat, longitude=lon)
        print(f"DEBUG: weather = {weather}")  # Отладочный вывод
        if weather:
            try:
                air_pollution = weather_app.get_air_pollution(lat, lon)
                print(f"DEBUG: air_pollution = {air_pollution}")  # Отладочный вывод
                text = format_extended_weather(weather, air_pollution)
            except Exception as e:
                # Если не удалось получить загрязнение воздуха, показываем обычную погоду
                import traceback
                print(f"Ошибка получения загрязнения воздуха: {e}\n{traceback.format_exc()}")
                text = format_extended_weather(weather, None)
            
            try:
                sent_msg = bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=create_main_menu())
                print(f"DEBUG: Расширенные данные (гео) отправлены успешно, message_id={sent_msg.message_id}")
            except Exception as e:
                print(f"DEBUG: Ошибка при отправке расширенных данных (гео): {e}")
                import traceback
                print(traceback.format_exc())
                # Пробуем отправить без HTML
                try:
                    import re
                    text_plain = re.sub(r'<[^>]+>', '', text)
                    bot.send_message(call.message.chat.id, text_plain, reply_markup=create_main_menu())
                except Exception as e2:
                    bot.send_message(call.message.chat.id, f"❌ Ошибка при отправке данных: {str(e2)}", reply_markup=create_main_menu())
        else:
            bot.send_message(call.message.chat.id, "❌ Не удалось получить данные", reply_markup=create_main_menu())
    except Exception as e:
        import traceback
        error_msg = f"❌ Ошибка: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Логируем полную ошибку
        bot.send_message(call.message.chat.id, f"❌ Ошибка: {str(e)}", reply_markup=create_main_menu())

# Обработчик кнопки "Назад в меню"
@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_menu(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_menu())

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен!")
    bot.infinity_polling()
