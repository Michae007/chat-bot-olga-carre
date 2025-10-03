import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
import sqlite3
from datetime import datetime, timedelta
import re
import json
from typing import Dict, List

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    BOT_TOKEN = os.environ.get('Olga_Carre')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

# Конфигурация
MASTER_PHONE = "+79507050964"
MASTER_CHAT_ID = None
WORKING_HOURS = {"start": "09:00", "end": "20:00"}
BREAK_TIME = "13:00-14:00"  # Обеденный перерыв

# Состояния разговора
SERVICE, DATE, TIME, NAME, PHONE, CONFIRM, MASTER_MENU = range(7)

# База услуг с детализацией
SERVICES = {
    "haircut_woman": {"name": "💇 Женская стрижка", "price": 1500, "duration": 60},
    "haircut_man": {"name": "💇‍♂️ Мужская стрижка", "price": 800, "duration": 45},
    "haircut_child": {"name": "👧 Детская стрижка", "price": 700, "duration": 40},
    "coloring": {"name": "🎨 Окрашивание", "price": 2500, "duration": 120},
    "styling": {"name": "💫 Укладка", "price": 1000, "duration": 30},
    "haircare": {"name": "🧖 Лечение волос", "price": 1200, "duration": 45},
    "complex": {"name": "✨ Комплекс (стрижка+укладка)", "price": 2200, "duration": 90}
}

# Инициализация расширенной базы данных
def init_db():
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    # Основная таблица записей
    cursor.execute('''CREATE TABLE IF NOT EXISTS appointments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  service TEXT,
                  service_key TEXT,
                  price INTEGER,
                  duration INTEGER,
                  date TEXT,
                  time TEXT,
                  name TEXT,
                  phone TEXT,
                  status TEXT DEFAULT 'active',
                  notes TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица доходов
    cursor.execute('''CREATE TABLE IF NOT EXISTS earnings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  amount INTEGER,
                  appointments_count INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица клиентов
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT UNIQUE,
                  name TEXT,
                  visits_count INTEGER DEFAULT 0,
                  last_visit TEXT,
                  total_spent INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

# Команда /start с улучшенным меню
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем, является ли пользователь мастером
    if update.effective_user.phone_number and MASTER_PHONE in update.effective_user.phone_number:
        global MASTER_CHAT_ID
        MASTER_CHAT_ID = update.effective_user.id
        await show_master_dashboard(update, context)
        return
    
    welcome_text = (
        f"👋 <b>Добро пожаловать, {user.first_name}!</b>\n\n"
        f"✨ <b>Салон красоты 'Ольга Карре'</b>\n\n"
        "💫 <b>Мы предлагаем:</b>\n"
        "• Профессиональные стрижки\n"
        "• Модное окрашивание\n"
        "• Уход за волосами\n"
        "• Стильные укладки\n\n"
        "📋 <b>Основные команды:</b>\n"
        "• /book - 📝 Новая запись\n"
        "• /my_bookings - 📋 Мои записи\n"
        "• /services - 💰 Услуги и цены\n"
        "• /reviews - ⭐ Отзывы\n"
        "• /contacts - 📞 Контакты\n\n"
        "🎁 <b>Акция:</b> 5-я стрижка со скидкой 20%!"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться", callback_data="quick_book")],
        [InlineKeyboardButton("💰 Услуги и цены", callback_data="show_services")],
        [InlineKeyboardButton("📞 Контакты", callback_data="show_contacts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

# Панель управления для мастера
async def show_master_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    # Статистика на сегодня
    today = datetime.now().strftime('%d.%m.%Y')
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(price), 0) 
        FROM appointments 
        WHERE date = ? AND status = 'active'
    """, (today,))
    today_stats = cursor.fetchone()
    
    # Статистика за месяц
    month_start = datetime.now().replace(day=1).strftime('%d.%m.%Y')
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(price), 0) 
        FROM appointments 
        WHERE date >= ? AND status = 'active'
    """, (month_start,))
    month_stats = cursor.fetchone()
    
    # Ближайшие записи
    cursor.execute("""
        SELECT time, name, service 
        FROM appointments 
        WHERE date = ? AND status = 'active'
        ORDER BY time
        LIMIT 3
    """, (today,))
    next_appointments = cursor.fetchall()
    
    conn.close()
    
    dashboard_text = (
        "👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ МАСТЕРА</b>\n\n"
        f"📊 <b>Сегодня ({today}):</b>\n"
        f"   • Записей: {today_stats[0]}\n"
        f"   • Ожидаемый доход: {today_stats[1]}₽\n\n"
        f"📈 <b>За этот месяц:</b>\n"
        f"   • Записей: {month_stats[0]}\n"
        f"   • Доход: {month_stats[1]}₽\n\n"
    )
    
    if next_appointments:
        dashboard_text += "⏰ <b>Ближайшие записи:</b>\n"
        for app in next_appointments:
            dashboard_text += f"   • {app[0]} - {app[1]} ({app[2]})\n"
    
    keyboard = [
        [InlineKeyboardButton("📅 Расписание на сегодня", callback_data="master_today")],
        [InlineKeyboardButton("📋 Все записи", callback_data="master_all")],
        [InlineKeyboardButton("📊 Статистика", callback_data="master_stats")],
        [InlineKeyboardButton("👥 База клиентов", callback_data="master_clients")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="master_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(dashboard_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.callback_query.edit_message_text(dashboard_text, reply_markup=reply_markup, parse_mode='HTML')

# Улучшенный процесс записи
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []
    for i, (key, service) in enumerate(SERVICES.items()):
        btn_text = f"{service['name']} - {service['price']}₽"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"service_{key}"))
        if (i + 1) % 1 == 0:  # По одной кнопке в строке для читаемости
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "✨ <b>Выберите услугу:</b>\n\n"
        "💡 <i>Нажмите на услугу для подробного описания</i>"
    )
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    return SERVICE

# Обработка выбора услуги с описанием
async def service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.replace('service_', '')
    service = SERVICES[service_key]
    
    context.user_data['service'] = service['name']
    context.user_data['service_key'] = service_key
    context.user_data['price'] = service['price']
    context.user_data['duration'] = service['duration']
    
    # Показываем описание услуги и просим подтверждение
    service_info = (
        f"✨ <b>{service['name']}</b>\n\n"
        f"💰 <b>Стоимость:</b> {service['price']}₽\n"
        f"⏱ <b>Время:</b> {service['duration']} мин.\n\n"
    )
    
    if service_key == "haircut_woman":
        service_info += "• Консультация стилиста\n• Мытье головы\n• Стрижка\n• Укладка"
    elif service_key == "coloring":
        service_info += "• Консультация по цвету\n• Подбор краски\n• Окрашивание\n• Уход после процедуры"
    
    keyboard = [
        [InlineKeyboardButton("✅ Выбрать эту услугу", callback_data=f"confirm_service_{service_key}")],
        [InlineKeyboardButton("◀️ К выбору услуг", callback_data="back_to_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(service_info, reply_markup=reply_markup, parse_mode='HTML')

# Подтверждение выбора услуги
async def confirm_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Показываем календарь на 14 дней
    keyboard = []
    today = datetime.now().date()
    
    # Заголовок с месяцами
    month_year = today.strftime('%B %Y')
    keyboard.append([InlineKeyboardButton(f"📅 {month_year}", callback_data="current_month")])
    
    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])
    
    # Даты
    row = []
    for i in range(14):
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Только рабочие дни
            date_str = date.strftime('%d.%m.%Y')
            day_num = date.strftime('%d')
            weekday = week_days[date.weekday()]
            
            # Проверяем доступность даты
            conn = sqlite3.connect('appointments.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status = 'active'", (date_str,))
            appointment_count = cursor.fetchone()[0]
            conn.close()
            
            # Максимум 10 записей в день
            if appointment_count < 10:
                btn_text = f"{day_num}\n{weekday}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"date_{date_str}"))
            else:
                btn_text = f"❌\n{weekday}"
                row.append(InlineKeyboardButton(btn_text, callback_data="ignore"))
            
            if len(row) == 7:
                keyboard.append(row)
                row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 <b>Выберите дату:</b>\n\n"
        f"💇 Услуга: <b>{context.user_data['service']}</b>\n"
        f"💰 Стоимость: <b>{context.user_data['price']}₽</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return DATE

# Система отзывов
async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reviews_text = (
        "⭐ <b>Отзывы наших клиентов:</b>\n\n"
        "★★★★★ <b>Анна:</b>\n"
        "<i>«Ольга - волшебница! Делает именно ту стрижку, которую хочу. Очень довольна!»</i>\n\n"
        "★★★★★ <b>Мария:</b>\n"
        "<i>«Хожу уже 3 года. Всегда профессионально, красиво и душевно. Рекомендую!»</i>\n\n"
        "★★★★★ <b>Елена:</b>\n"
        "<i>«Лучший мастер в городе! Цвет волос подобрала идеально. Спасибо!»</i>\n\n"
        "💫 <b>Оставьте свой отзыв:</b>\n"
        "Напишите сообщение с пометкой #отзыв"
    )
    
    await update.message.reply_text(reviews_text, parse_mode='HTML')

# Обработка текстовых сообщений (для отзывов)
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if "#отзыв" in text.lower():
        # Пересылаем отзыв мастеру
        if MASTER_CHAT_ID:
            review_text = (
                "⭐ <b>НОВЫЙ ОТЗЫВ!</b>\n\n"
                f"👤 <b>От:</b> {update.effective_user.first_name}\n"
                f"📝 <b>Текст:</b> {text.replace('#отзыв', '').strip()}\n"
                f"⏰ <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            
            try:
                app = context.application
                await app.bot.send_message(
                    chat_id=MASTER_CHAT_ID,
                    text=review_text,
                    parse_mode='HTML'
                )
                await update.message.reply_text("✅ Спасибо за ваш отзыв! Он очень важен для нас. 🌟")
            except Exception as e:
                logger.error(f"Ошибка отправки отзыва: {e}")

# Улучшенная система напоминаний
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправка напоминаний о записях"""
    try:
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        
        # Находим записи на завтра
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        cursor.execute("""
            SELECT phone, name, time, service 
            FROM appointments 
            WHERE date = ? AND status = 'active'
        """, (tomorrow,))
        
        appointments = cursor.fetchall()
        conn.close()
        
        for phone, name, time, service in appointments:
            reminder_text = (
                "🔔 <b>НАПОМИНАНИЕ О ЗАПИСИ</b>\n\n"
                f"👋 Здравствуйте, {name}!\n"
                f"Напоминаем, что завтра <b>{tomorrow}</b> в <b>{time}</b>\n"
                f"у вас запись: <b>{service}</b>\n\n"
                f"📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n"
                f"📱 <b>Телефон:</b> +79507050964\n\n"
                "💡 <b>Пожалуйста:</b>\n"
                "• Не опаздывайте\n"
                "• При отмене сообщите заранее\n"
                "• Оплата наличными или картой\n\n"
                "Ждем вас! 💫"
            )
            
            # Здесь должна быть логика отправки SMS или другого уведомления
            # Пока просто логируем
            logger.info(f"Напоминание для {name} ({phone}): {tomorrow} в {time}")
            
    except Exception as e:
        logger.error(f"Ошибка отправки напоминаний: {e}")

# Расширенная статистика для мастера
async def show_master_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    # Статистика за последние 30 дней
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    
    # Популярные услуги
    cursor.execute("""
        SELECT service, COUNT(*), SUM(price) 
        FROM appointments 
        WHERE date >= ? AND status = 'active'
        GROUP BY service 
        ORDER BY COUNT(*) DESC
    """, (month_ago,))
    popular_services = cursor.fetchall()
    
    # Постоянные клиенты
    cursor.execute("""
        SELECT name, phone, visits_count, total_spent 
        FROM clients 
        WHERE visits_count > 1 
        ORDER BY visits_count DESC 
        LIMIT 5
    """)
    regular_clients = cursor.fetchall()
    
    conn.close()
    
    stats_text = "📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
    
    stats_text += "🔥 <b>Популярные услуги:</b>\n"
    for service, count, revenue in popular_services:
        stats_text += f"• {service}: {count} зап. ({revenue}₽)\n"
    
    stats_text += "\n👥 <b>Постоянные клиенты:</b>\n"
    for name, phone, visits, spent in regular_clients:
        stats_text += f"• {name}: {visits} визитов ({spent}₽)\n"
    
    await update.callback_query.edit_message_text(stats_text, parse_mode='HTML')

# База клиентов для мастера
async def show_clients_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name, phone, visits_count, total_spent, last_visit 
        FROM clients 
        ORDER BY visits_count DESC
    """)
    clients = cursor.fetchall()
    conn.close()
    
    clients_text = "👥 <b>БАЗА КЛИЕНТОВ</b>\n\n"
    
    for name, phone, visits, spent, last_visit in clients[:10]:  # Показываем первых 10
        clients_text += (
            f"👤 <b>{name}</b>\n"
            f"   📱 {phone}\n"
            f"   🎯 Визитов: {visits}\n"
            f"   💰 Потратил: {spent}₽\n"
            f"   📅 Последний: {last_visit}\n\n"
        )
    
    if not clients:
        clients_text += "📭 Клиентов пока нет"
    
    await update.callback_query.edit_message_text(clients_text, parse_mode='HTML')

# Обработчик callback queries для мастера
async def master_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "master_today":
        await show_master_today_appointments(update, context)
    elif query.data == "master_all":
        await show_all_appointments(update, context)
    elif query.data == "master_stats":
        await show_master_stats(update, context)
    elif query.data == "master_clients":
        await show_clients_database(update, context)
    elif query.data == "master_settings":
        await show_master_settings(update, context)
    elif query.data == "back_to_dashboard":
        await show_master_dashboard(update, context)

# Показ записей на сегодня для мастера
async def show_master_today_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%d.%m.%Y')
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, time, name, phone, service, price, notes 
        FROM appointments 
        WHERE date = ? AND status = 'active'
        ORDER BY time
    """, (today,))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        text = f"📭 <b>На сегодня ({today}) записей нет</b>"
    else:
        text = f"📅 <b>РАСПИСАНИЕ НА СЕГОДНЯ ({today})</b>\n\n"
        total_income = 0
        
        for app in appointments:
            total_income += app[5]
            notes = f"\n   📝 <i>{app[6]}</i>" if app[6] else ""
            text += (
                f"🕒 <b>{app[1]}</b>\n"
                f"   👤 {app[2]}\n"
                f"   📱 {app[3]}\n"
                f"   💇 {app[4]}\n"
                f"   💰 {app[5]}₽{notes}\n"
                f"   🆔 #{app[0]}\n\n"
            )
        
        text += f"💰 <b>Ожидаемый доход: {total_income}₽</b>"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_dashboard")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

# Настройки мастера
async def show_master_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_text = (
        "⚙️ <b>НАСТРОЙКИ МАСТЕРА</b>\n\n"
        "🔔 <b>Уведомления:</b> Включены\n"
        "📱 <b>Телефон:</b> +79507050964\n"
        "🕒 <b>График работы:</b> 9:00-20:00\n"
        "🍽 <b>Перерыв:</b> 13:00-14:00\n\n"
        "<i>Для изменения настроек обратитесь к администратору</i>"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_dashboard")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(settings_text, reply_markup=reply_markup, parse_mode='HTML')

# Остальные функции (date_handler, time_handler, name, phone, confirm_handler, etc.)
# остаются аналогичными предыдущей версии, но с улучшениями...

def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем job для напоминаний (каждый день в 19:00)
    job_queue = application.job_queue
    job_queue.run_daily(send_reminders, time=datetime.strptime("19:00", "%H:%M").time())
    
    # Обработчики для мастера
    application.add_handler(CallbackQueryHandler(master_callback_handler, pattern="^master_"))
    application.add_handler(CallbackQueryHandler(master_callback_handler, pattern="^back_to_dashboard"))
    
    # Обработчик текстовых сообщений для отзывов
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Остальные обработчики...
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reviews", show_reviews))
    application.add_handler(CommandHandler("master", show_master_dashboard))
    
    # ConversationHandler для записи...
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            SERVICE: [
                CallbackQueryHandler(service_handler, pattern='^service_'),
                CallbackQueryHandler(confirm_service_handler, pattern='^confirm_service_')
            ],
            DATE: [CallbackQueryHandler(date_handler, pattern='^(date_|cancel|ignore|current_month)$')],
            # ... остальные states
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(conv_handler)
    
    application.run_polling()

if __name__ == '__main__':
    main()
