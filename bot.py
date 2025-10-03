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

# Обработка callback queries для главного меню - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def handle_main_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "quick_book":
        await book_callback(update, context)
    elif query.data == "show_services":
        await show_services_callback(update, context)
    elif query.data == "show_contacts":
        await show_contacts_callback(update, context)
    elif query.data == "leave_review":
        await leave_review_callback(update, context)

# Быстрая запись через кнопку
async def book_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for key, service in SERVICES.items():
        btn_text = f"{service['name']} - {service['price']}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"service_{key}")])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "✨ <b>Выберите услугу:</b>"
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

# Улучшенный процесс записи через команду
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for key, service in SERVICES.items():
        btn_text = f"{service['name']} - {service['price']}₽"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"service_{key}")])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "✨ <b>Выберите услугу:</b>"
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    return SERVICE

# Показ услуг через callback - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def show_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    services_text = "✨ <b>НАШИ УСЛУГИ И ЦЕНЫ</b>\n\n"
    
    for service in SERVICES.values():
        services_text += f"• {service['name']} - {service['price']}₽\n"
        services_text += f"  ⏱ {service['duration']} мин.\n\n"
    
    services_text += (
        "🕒 <b>Время работы:</b>\n"
        "• Пн-Пт: 9:00 - 20:00\n"
        "• Сб-Вс: 10:00 - 18:00\n\n"
        "🍽 <b>Обеденный перерыв:</b> 13:00-14:00"
    )
    
    keyboard = [[InlineKeyboardButton("📝 Записаться", callback_data="quick_book")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Используем edit_message_text вместо reply_text для callback query
    await query.edit_message_text(services_text, reply_markup=reply_markup, parse_mode='HTML')

# Показ услуг через команду
async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services_text = "✨ <b>НАШИ УСЛУГИ И ЦЕНЫ</b>\n\n"
    
    for service in SERVICES.values():
        services_text += f"• {service['name']} - {service['price']}₽\n"
        services_text += f"  ⏱ {service['duration']} мин.\n\n"
    
    services_text += (
        "🕒 <b>Время работы:</b>\n"
        "• Пн-Пт: 9:00 - 20:00\n"
        "• Сб-Вс: 10:00 - 18:00\n\n"
        "🍽 <b>Обеденный перерыв:</b> 13:00-14:00"
    )
    
    keyboard = [[InlineKeyboardButton("📝 Записаться", callback_data="quick_book")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(services_text, reply_markup=reply_markup, parse_mode='HTML')

# Контакты через callback - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def show_contacts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    contacts_text = (
        "📞 <b>КОНТАКТЫ САЛОНА</b>\n\n"
        "👩‍💼 <b>Мастер:</b> Ольга Карре\n"
        f"📱 <b>Телефон:</b> {MASTER_PHONE}\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n\n"
        "🕒 <b>Время работы:</b>\n"
        "• Пн-Пт: 9:00 - 20:00\n"
        "• Сб-Вс: 10:00 - 18:00\n\n"
        "🚇 <b>Как добраться:</b>\n"
        "Метро 'Красивая', 5 минут пешком\n"
        "Рядом бесплатная парковка"
    )
    
    await query.edit_message_text(contacts_text, parse_mode='HTML')

# Контакты через команду
async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contacts_text = (
        "📞 <b>КОНТАКТЫ САЛОНА</b>\n\n"
        "👩‍💼 <b>Мастер:</b> Ольга Карре\n"
        f"📱 <b>Телефон:</b> {MASTER_PHONE}\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n\n"
        "🕒 <b>Время работы:</b>\n"
        "• Пн-Пт: 9:00 - 20:00\n"
        "• Сб-Вс: 10:00 - 18:00\n\n"
        "🚇 <b>Как добраться:</b>\n"
        "Метро 'Красивая', 5 минут пешком\n"
        "Рядом бесплатная парковка"
    )
    
    await update.message.reply_text(contacts_text, parse_mode='HTML')

# Оставить отзыв через callback - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def leave_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⭐ <b>ОСТАВЬТЕ ОТЗЫВ</b>\n\n"
        "Пожалуйста, отправьте ваш отзыв в формате:\n\n"
        "<code>Имя\nОценка (1-5)\nТекст отзыва</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>Анна\n5\nОльга - волшебница! Стрижка идеальная!</code>",
        parse_mode='HTML'
    )

# Система отзывов через команду
async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("SELECT client_name, rating, text FROM reviews ORDER BY created_at DESC LIMIT 5")
    reviews = cursor.fetchall()
    conn.close()
    
    if reviews:
        reviews_text = "⭐ <b>ПОСЛЕДНИЕ ОТЗЫВЫ:</b>\n\n"
        for name, rating, text in reviews:
            stars = "★" * rating + "☆" * (5 - rating)
            reviews_text += f"{stars} <b>{name}:</b>\n<i>«{text}»</i>\n\n"
    else:
        reviews_text = (
            "⭐ <b>ОТЗЫВЫ КЛИЕНТОВ</b>\n\n"
            "Пока нет отзывов. Будьте первым!\n\n"
        )
    
    reviews_text += "💫 <b>Оставить отзыв:</b>\nНажмите кнопку ниже"
    
    keyboard = [[InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(reviews_text, reply_markup=reply_markup, parse_mode='HTML')

# Обработка отзывов
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lines = text.split('\n')
    
    if len(lines) < 3:
        await update.message.reply_text(
            "❌ <b>Неверный формат отзыва!</b>\n\n"
            "Пожалуйста, используйте формат:\n"
            "<code>Имя\nОценка (1-5)\nТекст отзыва</code>",
            parse_mode='HTML'
        )
        return
    
    name = lines[0].strip()
    try:
        rating = int(lines[1].strip())
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Оценка должна быть числом от 1 до 5")
        return
    
    review_text = '\n'.join(lines[2:]).strip()
    
    # Сохраняем отзыв
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reviews (client_name, rating, text) VALUES (?, ?, ?)",
                   (name, rating, review_text))
    conn.commit()
    conn.close()
    
    # Уведомляем мастера
    if MASTER_CHAT_ID:
        review_notification = (
            "⭐ <b>НОВЫЙ ОТЗЫВ!</b>\n\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"⭐ <b>Оценка:</b> {'★' * rating}{'☆' * (5 - rating)}\n"
            f"📝 <b>Текст:</b> {review_text}\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        try:
            app = context.application
            await app.bot.send_message(
                chat_id=MASTER_CHAT_ID,
                text=review_notification,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка отправки отзыва мастеру: {e}")
    
    await update.message.reply_text(
        "✅ <b>Спасибо за ваш отзыв!</b>\n\n"
        "Мы очень ценим ваше мнение! 🌟",
        parse_mode='HTML'
    )

# Просмотр записей клиента
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.replace('/my_bookings', '').strip()
    
    if not user_input:
        await update.message.reply_text(
            "📋 <b>ПРОСМОТР ЗАПИСЕЙ</b>\n\n"
            "Введите номер телефона:\n"
            "<code>/my_bookings +79123456789</code>\n\n"
            "👑 <b>Для мастера:</b>\n"
            "<code>/master +79507050964</code> - все записи\n"
            "<code>/master_today +79507050964</code> - на сегодня",
            parse_mode='HTML'
        )
        return
    
    # Нормализация телефона
    phone = user_input
    phone_clean = phone.replace(' ', '').replace('-', '')
    if phone_clean.startswith('8'):
        phone = '+7' + phone_clean[1:]
    elif phone_clean.startswith('7'):
        phone = '+' + phone_clean
    elif not phone_clean.startswith('+7'):
        phone = '+7' + phone_clean
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, service, date, time, status, price
        FROM appointments 
        WHERE phone = ? 
        ORDER BY date DESC, time DESC
        LIMIT 10
    """, (phone,))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        await update.message.reply_text("❌ Записей не найдено. Проверьте номер телефона.")
        return
    
    text = "📋 <b>ВАШИ ЗАПИСИ:</b>\n\n"
    for app in appointments:
        status_icon = "✅" if app[4] == 'active' else "❌"
        status_text = "Активна" if app[4] == 'active' else "Отменена"
        text += (f"{status_icon} <b>ID:</b> #{app[0]}\n"
                f"   💇 <b>Услуга:</b> {app[1]}\n"
                f"   💰 <b>Стоимость:</b> {app[5]}₽\n"
                f"   📅 <b>Дата:</b> {app[2]}\n"
                f"   🕒 <b>Время:</b> {app[3]}\n"
                f"   📊 <b>Статус:</b> {status_text}\n\n")
    
    text += "💡 <b>Для отмены записи:</b>\n<code>/cancel_booking ID_записи</code>"
    
    await update.message.reply_text(text, parse_mode='HTML')

# Команды для мастера
async def master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.replace('/master', '').replace('/master_today', '').strip()
    
    # Простая проверка мастера по номеру телефона
    if user_input != MASTER_PHONE:
        await update.message.reply_text("❌ Эта команда только для мастера.")
        return
    
    global MASTER_CHAT_ID
    if not MASTER_CHAT_ID:
        MASTER_CHAT_ID = update.effective_user.id
        logger.info(f"Master chat_id set: {MASTER_CHAT_ID}")
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    
    if 'today' in update.message.text:
        # Записи на сегодня
        today = datetime.now().strftime('%d.%m.%Y')
        cursor.execute("""
            SELECT id, service, time, name, phone, price
            FROM appointments 
            WHERE date = ? AND status = 'active'
            ORDER BY time
        """, (today,))
        appointments = cursor.fetchall()
        
        if not appointments:
            await update.message.reply_text(f"📭 На сегодня ({today}) записей нет.")
            conn.close()
            return
        
        text = f"📅 <b>ЗАПИСИ НА СЕГОДНЯ ({today}):</b>\n\n"
        total = 0
        for app in appointments:
            total += app[5]
            text += (f"🕒 <b>{app[2]}</b>\n"
                    f"   👤 {app[3]}\n"
                    f"   📱 {app[4]}\n"
                    f"   💇 {app[1]}\n"
                    f"   💰 {app[5]}₽\n"
                    f"   🆔 #{app[0]}\n\n")
        
        text += f"💰 <b>Ожидаемый доход: {total}₽</b>"
        
    else:
        # Все активные записи
        cursor.execute("""
            SELECT id, service, date, time, name, phone, price
            FROM appointments 
            WHERE status = 'active' AND date >= date('now')
            ORDER BY date, time
        """)
        appointments = cursor.fetchall()
        
        if not appointments:
            await update.message.reply_text("📭 Активных записей нет.")
            conn.close()
            return
        
        text = "📋 <b>ВСЕ АКТИВНЫЕ ЗАПИСИ:</b>\n\n"
        current_date = None
        for app in appointments:
            if app[3] != current_date:
                current_date = app[3]
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][datetime.strptime(current_date, '%d.%m.%Y').weekday()]
                text += f"\n📅 <b>{current_date} ({weekday})</b>\n"
            
            text += (f"   🕒 <b>{app[3]}</b> - {app[4]}\n"
                    f"      📱 {app[5]}\n"
                    f"      💇 {app[1]}\n"
                    f"      💰 {app[6]}₽\n"
                    f"      🆔 #{app[0]}\n")
    
    conn.close()
    await update.message.reply_text(text, parse_mode='HTML')

# Отмена записи
async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ <b>Укажите ID записи для отмены:</b>\n"
            "<code>/cancel_booking 123</code>\n\n"
            "📋 <b>Чтобы узнать ID записи:</b>\n"
            "<code>/my_bookings +79123456789</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        booking_id = int(args[0])
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM appointments WHERE id = ?", (booking_id,))
        appointment = cursor.fetchone()
        
        if not appointment:
            await update.message.reply_text("❌ Запись не найдена.")
            conn.close()
            return
        
        cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (booking_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ <b>Запись отменена</b>\n\n"
            f"📋 ID: #{booking_id}\n"
            f"💇 Услуга: {appointment[1]}\n"
            f"📅 Дата: {appointment[5]}\n"
            f"🕒 Время: {appointment[6]}\n"
            f"👤 Клиент: {appointment[7]}",
            parse_mode='HTML'
        )
        
    except (ValueError, sqlite3.Error) as e:
        await update.message.reply_text("❌ Ошибка при отмене записи. Проверьте ID.")

# Обработка ошибок
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
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
    application.add_handler(CallbackQueryHandler(handle_main_menu_callbacks, pattern='^(show_services|show_contacts|leave_review|quick_book)$'))
    
    # Обработчик отзывов
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review))
    
    application.add_error_handler(error)
    
    # Запуск бота
    logger.info("Бот запущен и готов к работе!")
    application.run_polling()

if __name__ == '__main__':
    main()
