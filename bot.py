import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
import sqlite3
from datetime import datetime, timedelta
import re

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

# Состояния разговора
SERVICE, DATE, TIME, NAME, PHONE, CONFIRM = range(6)

# База услуг с детализацией
SERVICES = {
    "haircut_woman": {"name": "💇 Женская стрижка", "price": 1500, "duration": 60},
    "haircut_man": {"name": "💇‍♂️ Мужская стрижка", "price": 800, "duration": 45},
    "haircut_child": {"name": "👧 Детская стрижка", "price": 700, "duration": 40},
    "coloring": {"name": "🎨 Окрашивание", "price": 2500, "duration": 120},
    "complex": {"name": "✨ Комплекс (стрижка+укладка)", "price": 2200, "duration": 90}
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
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
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT UNIQUE,
                  name TEXT,
                  visits_count INTEGER DEFAULT 0,
                  last_visit TEXT,
                  total_spent INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_name TEXT,
                  phone TEXT,
                  rating INTEGER,
                  text TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

# Обновляем информацию о клиенте
def update_client_info(name, phone, amount_spent):
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%d.%m.%Y')
    
    cursor.execute('''INSERT OR REPLACE INTO clients 
                    (phone, name, visits_count, last_visit, total_spent)
                    VALUES (?, ?, 
                    COALESCE((SELECT visits_count FROM clients WHERE phone = ?), 0) + 1,
                    ?, 
                    COALESCE((SELECT total_spent FROM clients WHERE phone = ?), 0) + ?)''',
                    (phone, name, phone, today, phone, amount_spent))
    
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_text = (
        f"👋 <b>Добро пожаловать, {user.first_name}!</b>\n\n"
        f"✨ <b>Салон красоты 'Ольга Карре'</b>\n\n"
        "💫 <b>Мы предлагаем:</b>\n"
        "• Профессиональные стрижки\n"
        "• Модное окрашивание\n"
        "• Стильные укладки\n\n"
        "📋 <b>Основные команды:</b>\n"
        "• /book - 📝 Новая запись\n"
        "• /my_bookings - 📋 Мои записи\n"
        "• /services - 💰 Услуги и цены\n"
        "• /reviews - ⭐ Отзывы\n"
        "• /contacts - 📞 Контакты"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться онлайн", callback_data="quick_book")],
        [InlineKeyboardButton("💰 Услуги и цены", callback_data="show_services")],
        [InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review")],
        [InlineKeyboardButton("📞 Контакты", callback_data="show_contacts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

# Обработка callback queries для главного меню
async def handle_main_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    else:
        return
    
    logger.info(f"Обработка callback: {query.data}")
    
    try:
        if query.data == "quick_book":
            await quick_book_handler(update, context)
        elif query.data == "show_services":
            await show_services_callback(update, context)
        elif query.data == "show_contacts":
            await show_contacts_callback(update, context)
        elif query.data == "leave_review":
            await leave_review_callback(update, context)
        elif query.data == "my_bookings_list":
            await my_bookings_callback(update, context)
        elif query.data == "leave_review_after_booking":
            await leave_review_callback(update, context)
    except Exception as e:
        logger.error(f"Ошибка в обработчике callback: {e}")
        if query:
            await query.edit_message_text("❌ Произошла ошибка. Попробуйте еще раз.")

# Обработчик быстрой записи
async def quick_book_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, это callback query или обычное сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    logger.info("Начало процесса записи")
    
    # Создаем клавиатуру с услугами
    keyboard = []
    for key, service in SERVICES.items():
        btn_text = f"{service['name']} - {service['price']}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"service_{key}")])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "✨ <b>Выберите услугу:</b>"
    
    if update.callback_query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    return SERVICE

# Команда /book
async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quick_book_handler(update, context)

# Обработка выбора услуги
async def service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.replace('service_', '')
    service = SERVICES[service_key]
    
    context.user_data['service'] = service['name']
    context.user_data['service_key'] = service_key
    context.user_data['price'] = service['price']
    context.user_data['duration'] = service['duration']
    
    # Показываем календарь на 7 дней
    keyboard = []
    today = datetime.now().date()
    
    for i in range(7):
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Только рабочие дни (Пн-Пт)
            date_str = date.strftime('%d.%m.%Y')
            weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
            
            # Проверяем доступность даты
            conn = sqlite3.connect('appointments.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status = 'active'", (date_str,))
            appointment_count = cursor.fetchone()[0]
            conn.close()
            
            # Максимум 8 записей в день
            if appointment_count < 8:
                btn_text = f"{date_str} ({weekday})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"date_{date_str}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="quick_book")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 <b>Выберите дату:</b>\n\n"
        f"💇 Услуга: <b>{service['name']}</b>\n"
        f"💰 Стоимость: <b>{service['price']}₽</b>\n"
        f"⏱ Время: <b>{service['duration']} мин.</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return DATE

# Обработка выбора даты
async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_services":
        return await quick_book_handler(update, context)
    
    date_str = query.data.replace('date_', '')
    context.user_data['date'] = date_str
    
    # Показываем доступное время
    keyboard = []
    times = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
    
    # Проверяем занятые времена
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("SELECT time FROM appointments WHERE date = ? AND status = 'active'", (date_str,))
    busy_times = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    row = []
    for time in times:
        if time not in busy_times:
            row.append(InlineKeyboardButton(time, callback_data=f"time_{time}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_dates")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🕒 <b>Выберите время на {date_str}:</b>\n"
        f"Услуга: <b>{context.user_data['service']}</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return TIME

# Обработка выбора времени - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_dates":
        # Возвращаемся к выбору даты
        service_key = context.user_data.get('service_key')
        if service_key:
            service = SERVICES[service_key]
            context.user_data['service'] = service['name']
        
        keyboard = []
        today = datetime.now().date()
        
        for i in range(7):
            date = today + timedelta(days=i)
            if date.weekday() < 5:
                date_str = date.strftime('%d.%m.%Y')
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
                
                conn = sqlite3.connect('appointments.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status = 'active'", (date_str,))
                appointment_count = cursor.fetchone()[0]
                conn.close()
                
                if appointment_count < 8:
                    btn_text = f"{date_str} ({weekday})"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"date_{date_str}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад к услугам", callback_data="quick_book")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📅 <b>Выберите дату:</b>\n\n"
            f"💇 Услуга: <b>{context.user_data['service']}</b>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return DATE
    
    time_str = query.data.replace('time_', '')
    context.user_data['time'] = time_str
    
    # Вместо edit_message_text используем send_message для нового сообщения
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="✏️ <b>Введите ваше имя:</b>\n\n<i>Как к вам обращаться?</i>",
        parse_mode='HTML'
    )
    
    return NAME

# Ввод имени
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text(
        "📱 <b>Введите ваш номер телефона:</b>\n\n"
        "<i>Пример: +79123456789 или 89123456789</i>",
        parse_mode='HTML'
    )
    return PHONE

# Ввод телефона
async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    # Проверка формата телефона
    phone_clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not re.match(r'^(\+7|8|7)?\d{10}$', phone_clean):
        await update.message.reply_text(
            "❌ <b>Неверный формат телефона!</b>\n\n"
            "Введите номер в формате:\n"
            "+79123456789 или 89123456789",
            parse_mode='HTML'
        )
        return PHONE
    
    # Нормализация телефона
    if phone_clean.startswith('8'):
        phone = '+7' + phone_clean[1:]
    elif phone_clean.startswith('7'):
        phone = '+' + phone_clean
    elif not phone_clean.startswith('+7'):
        phone = '+7' + phone_clean
    
    context.user_data['phone'] = phone
    
    # Подтверждение записи
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить запись", callback_data="confirm_yes")],
        [InlineKeyboardButton("✏️ Изменить данные", callback_data="confirm_edit")],
        [InlineKeyboardButton("❌ Отменить", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    appointment_text = (
        "📋 <b>ПОДТВЕРЖДЕНИЕ ЗАПИСИ</b>\n\n"
        f"👤 <b>Имя:</b> {context.user_data['name']}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"💇 <b>Услуга:</b> {context.user_data['service']}\n"
        f"💰 <b>Стоимость:</b> {context.user_data['price']}₽\n"
        f"📅 <b>Дата:</b> {context.user_data['date']}\n"
        f"🕒 <b>Время:</b> {context.user_data['time']}\n\n"
        "<i>Все верно? Подтвердите запись</i>"
    )
    
    await update.message.reply_text(appointment_text, reply_markup=reply_markup, parse_mode='HTML')
    return CONFIRM

# Подтверждение записи
async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_no":
        await query.edit_message_text("❌ Запись отменена")
        return ConversationHandler.END
    
    if query.data == "confirm_edit":
        await query.edit_message_text("✏️ <b>Начнем запись заново:</b>", parse_mode='HTML')
        return await quick_book_handler(update, context)
    
    # Сохранение в базу данных
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO appointments 
                   (service, service_key, price, duration, date, time, name, phone) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   (context.user_data['service'], context.user_data['service_key'],
                    context.user_data['price'], context.user_data['duration'],
                    context.user_data['date'], context.user_data['time'],
                    context.user_data['name'], context.user_data['phone']))
    appointment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Обновляем информацию о клиенте
    update_client_info(context.user_data['name'], context.user_data['phone'], context.user_data['price'])
    
    # Уведомление для мастера
    master_text = (
        "🔔 <b>НОВАЯ ЗАПИСЬ!</b>\n\n"
        f"📋 <b>ID:</b> #{appointment_id}\n"
        f"👤 <b>Клиент:</b> {context.user_data['name']}\n"
        f"📱 <b>Телефон:</b> {context.user_data['phone']}\n"
        f"💇 <b>Услуга:</b> {context.user_data['service']}\n"
        f"💰 <b>Стоимость:</b> {context.user_data['price']}₽\n"
        f"📅 <b>Дата:</b> {context.user_data['date']}\n"
        f"🕒 <b>Время:</b> {context.user_data['time']}\n\n"
        f"⏰ Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    # Отправляем уведомление мастеру
    global MASTER_CHAT_ID
    if MASTER_CHAT_ID:
        try:
            app = context.application
            await app.bot.send_message(
                chat_id=MASTER_CHAT_ID,
                text=master_text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление мастеру: {e}")
    
    # Подтверждение клиенту
    success_text = (
        "✅ <b>ЗАПИСЬ ПОДТВЕРЖДЕНА!</b>\n\n"
        f"📋 <b>Детали записи:</b>\n"
        f"• ID: #{appointment_id}\n"
        f"• Услуга: {context.user_data['service']}\n"
        f"• Стоимость: {context.user_data['price']}₽\n"
        f"• Дата: {context.user_data['date']}\n"
        f"• Время: {context.user_data['time']}\n"
        f"• Имя: {context.user_data['name']}\n"
        f"• Телефон: {context.user_data['phone']}\n\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n"
        "📱 <b>Контакты:</b> +79507050964\n\n"
        "💡 <b>Важная информация:</b>\n"
        "• Отмена возможна за 2 часа до приема\n"
        "• Оплата наличными или картой\n"
        "• При отмене: /cancel_booking ID\n\n"
        "📞 <b>Если что-то изменится:</b>\n"
        "Позвоните по телефону выше\n\n"
        "Ждем вас! 💫"
    )
    
    keyboard = [
        [InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review_after_booking")],
        [InlineKeyboardButton("📋 Мои записи", callback_data="my_bookings_list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='HTML')
    
    # Сохраняем chat_id мастера
    if context.user_data['phone'] == MASTER_PHONE and not MASTER_CHAT_ID:
        MASTER_CHAT_ID = update.effective_user.id
        logger.info(f"Master chat_id saved: {MASTER_CHAT_ID}")
    
    return ConversationHandler.END

# Остальные функции (show_services_callback, show_contacts_callback, и т.д.) остаются без изменений
# ...

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик диалога записи через ConversationHandler - ИСПРАВЛЕННАЯ ВЕРСИЯ
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('book', book_command),
            CallbackQueryHandler(quick_book_handler, pattern='^quick_book$')
        ],
        states={
            SERVICE: [
                CallbackQueryHandler(service_handler, pattern='^service_'),
            ],
            DATE: [
                CallbackQueryHandler(date_handler, pattern='^date_'),
                CallbackQueryHandler(quick_book_handler, pattern='^back_to_services$')
            ],
            TIME: [
                CallbackQueryHandler(time_handler, pattern='^time_'),
                CallbackQueryHandler(date_handler, pattern='^back_to_dates$')
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            CONFIRM: [CallbackQueryHandler(confirm_handler, pattern='^confirm_')]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel, pattern='^cancel_booking$'),
            CallbackQueryHandler(cancel, pattern='^confirm_no$')
        ],
        per_message=False
    )
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("services", show_services))
    application.add_handler(CommandHandler("contacts", show_contacts))
    application.add_handler(CommandHandler("reviews", show_reviews))
    application.add_handler(CommandHandler("my_bookings", my_bookings))
    application.add_handler(CommandHandler("master", master_command))
    application.add_handler(CommandHandler("master_today", master_command))
    application.add_handler(CommandHandler("cancel_booking", cancel_booking))
    
    # Обработчики callback queries для главного меню
    application.add_handler(CallbackQueryHandler(handle_main_menu_callbacks, pattern='^(show_services|show_contacts|leave_review|my_bookings_list|leave_review_after_booking)$'))
    
    # Обработчик отзывов
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review))
    
    # ConversationHandler должен быть добавлен последним
    application.add_handler(conv_handler)
    application.add_error_handler(error)
    
    # Запуск бота
    logger.info("Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == '__main__':
    main()
