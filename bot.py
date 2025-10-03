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

# Номер телефона мастера
MASTER_PHONE = "+79507050964"
MASTER_CHAT_ID = None  # Будет установлен при первом использовании

# Определение состояний разговора
SERVICE, DATE, TIME, NAME, PHONE, CONFIRM = range(6)

# Услуги парикмахера
SERVICES = {
    "haircut_woman": "💇 Женская стрижка - 1500₽",
    "haircut_man": "💇‍♂️ Мужская стрижка - 800₽", 
    "haircut_child": "👧 Детская стрижка - 700₽",
    "coloring": "🎨 Окрашивание - 2500₽",
    "styling": "💫 Укладка - 1000₽",
    "haircare": "🧖 Лечение волос - 1200₽"
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS appointments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  service TEXT,
                  date TEXT,
                  time TEXT,
                  name TEXT,
                  phone TEXT,
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Здравствуйте, {user.first_name}!\n"
        f"Добро пожаловать в салон красоты 'Ольга Карре'!\n\n"
        "✨ <b>Наши услуги:</b>\n"
        "• 💇 Женская стрижка - 1500₽\n"
        "• 💇‍♂️ Мужская стрижка - 800₽\n" 
        "• 👧 Детская стрижка - 700₽\n"
        "• 🎨 Окрашивание - 2500₽\n"
        "• 💫 Укладка - 1000₽\n"
        "• 🧖 Лечение волос - 1200₽\n\n"
        "📅 <b>Команды:</b>\n"
        "/book - 📝 Записаться на прием\n"
        "/my_bookings - 📋 Мои записи\n"
        "/cancel_booking - ❌ Отменить запись\n"
        "/services - 💰 Услуги и цены\n"
        "/contacts - 📞 Контакты",
        parse_mode='HTML'
    )

# Показать услуги и цены
async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services_text = "✨ <b>Наши услуги и цены:</b>\n\n"
    for service in SERVICES.values():
        services_text += f"• {service}\n"
    
    services_text += "\n🕒 <b>Время работы:</b>\n"
    services_text += "• Пн-Пт: 9:00 - 20:00\n"
    services_text += "• Сб-Вс: 10:00 - 18:00\n\n"
    services_text += "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15"
    
    await update.message.reply_text(services_text, parse_mode='HTML')

# Контакты
async def contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contacts_text = (
        "📞 <b>Контакты салона:</b>\n\n"
        "👩‍💼 <b>Мастер:</b> Ольга\n"
        f"📱 <b>Телефон:</b> {MASTER_PHONE}\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n"
        "🕒 <b>Время работы:</b>\n"
        "   Пн-Пт: 9:00 - 20:00\n"
        "   Сб-Вс: 10:00 - 18:00\n\n"
        "💬 <b>Как добраться:</b>\n"
        "Метро 'Красивая', 5 минут пешком"
    )
    await update.message.reply_text(contacts_text, parse_mode='HTML')

# Начало процесса записи
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []
    for i, (key, service) in enumerate(SERVICES.items()):
        row.append(InlineKeyboardButton(service, callback_data=f"service_{key}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "✨ Выберите услугу:",
        reply_markup=reply_markup
    )
    return SERVICE

# Обработка выбора услуги
async def service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.replace('service_', '')
    context.user_data['service'] = SERVICES[service_key]
    context.user_data['service_key'] = service_key
    
    # Показываем доступные даты (ближайшие 7 дней)
    keyboard = []
    today = datetime.now().date()
    row = []
    for i in range(7):
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Пн-Пт
            date_str = date.strftime('%d.%m.%Y')
            weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
            row.append(InlineKeyboardButton(f"{date_str} ({weekday})", callback_data=f"date_{date_str}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📅 Выберите дату для услуги:\n<b>{context.user_data['service']}</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return DATE

# Обработка выбора даты
async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Запись отменена")
        return ConversationHandler.END
    
    date_str = query.data.replace('date_', '')
    context.user_data['date'] = date_str
    
    # Показываем доступное время
    keyboard = []
    times = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
    
    # Проверяем какие времена заняты
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
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_services"), 
                    InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if not any(button.callback_data.startswith('time_') for row in keyboard for button in row):
        await query.edit_message_text(
            f"❌ На {date_str} нет свободного времени. Выберите другую дату.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Выбрать другую дату", callback_data="back_to_dates")]])
        )
        return DATE
    
    await query.edit_message_text(
        f"🕒 Выберите время для {date_str}:\nУслуга: <b>{context.user_data['service']}</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return TIME

# Обработка выбора времени
async def time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_services":
        return await service_handler(update, context)
    elif query.data == "back_to_dates":
        return await date_handler(update, context)
    
    time_str = query.data.replace('time_', '')
    context.user_data['time'] = time_str
    
    await query.edit_message_text(
        f"✏️ Введите ваше имя:",
        parse_mode='HTML'
    )
    return NAME

# Ввод имени
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text(
        "📱 Введите ваш номер телефона:\n\n"
        "<i>Пример: +79123456789 или 89123456789</i>",
        parse_mode='HTML'
    )
    return PHONE

# Ввод телефона
async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    # Проверка формата телефона
    if not re.match(r'^(\+7|8)?\d{10}$', phone.replace(' ', '').replace('-', '')):
        await update.message.reply_text(
            "❌ Неверный формат телефона!\n"
            "Введите номер в формате: +79123456789 или 89123456789"
        )
        return PHONE
    
    # Нормализация телефона
    if phone.startswith('8'):
        phone = '+7' + phone[1:]
    elif phone.startswith('7'):
        phone = '+' + phone
    elif not phone.startswith('+7'):
        phone = '+7' + phone
    
    context.user_data['phone'] = phone
    
    # Подтверждение записи
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить запись", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ Отменить", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    appointment_text = (
        "📋 <b>Подтвердите запись:</b>\n\n"
        f"👤 <b>Имя:</b> {context.user_data['name']}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"💇 <b>Услуга:</b> {context.user_data['service']}\n"
        f"📅 <b>Дата:</b> {context.user_data['date']}\n"
        f"🕒 <b>Время:</b> {context.user_data['time']}\n\n"
        "<i>Нажмите 'Подтвердить запись' для завершения</i>"
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
    
    # Сохранение в базу данных
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO appointments (service, date, time, name, phone) VALUES (?, ?, ?, ?, ?)",
                   (context.user_data['service'], context.user_data['date'],
                    context.user_data['time'], context.user_data['name'],
                    context.user_data['phone']))
    appointment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Уведомление для мастера
    master_text = (
        "🔔 <b>НОВАЯ ЗАПИСЬ!</b>\n\n"
        f"📋 <b>ID записи:</b> #{appointment_id}\n"
        f"👤 <b>Клиент:</b> {context.user_data['name']}\n"
        f"📱 <b>Телефон:</b> {context.user_data['phone']}\n"
        f"💇 <b>Услуга:</b> {context.user_data['service']}\n"
        f"📅 <b>Дата:</b> {context.user_data['date']}\n"
        f"🕒 <b>Время:</b> {context.user_data['time']}\n\n"
        f"⏰ Запись создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    # Отправляем уведомление мастеру (если известен chat_id)
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
        "✅ <b>Запись успешно создана!</b>\n\n"
        f"📋 <b>Детали записи:</b>\n"
        f"• ID: #{appointment_id}\n"
        f"• Услуга: {context.user_data['service']}\n"
        f"• Дата: {context.user_data['date']}\n"
        f"• Время: {context.user_data['time']}\n"
        f"• Имя: {context.user_data['name']}\n"
        f"• Телефон: {context.user_data['phone']}\n\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Красивая, д. 15\n"
        "📱 <b>Контакты:</b> +79507050964\n\n"
        "💡 <b>Важно:</b>\n"
        "• Отмена записи возможна за 2 часа до приема\n"
        "• Оплата наличными или картой\n"
        "• При отмене используйте команду /cancel_booking\n\n"
        "Ждем вас! 🎉"
    )
    
    await query.edit_message_text(success_text, parse_mode='HTML')
    
    # Сохраняем chat_id мастера при первой записи
    if context.user_data['phone'] == MASTER_PHONE and not MASTER_CHAT_ID:
        MASTER_CHAT_ID = update.effective_user.id
        logger.info(f"Master chat_id saved: {MASTER_CHAT_ID}")
    
    return ConversationHandler.END

# Просмотр записей клиента
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.replace('/my_bookings', '').strip()
    
    if not user_input:
        await update.message.reply_text(
            "📋 Для просмотра записей введите номер телефона:\n"
            "<code>/my_bookings +79123456789</code>\n\n"
            "👑 <b>Для мастера:</b>\n"
            "<code>/master</code> - все активные записи\n"
            "<code>/master_today</code> - записи на сегодня",
            parse_mode='HTML'
        )
        return
    
    # Нормализация телефона
    phone = user_input
    if phone.startswith('8'):
        phone = '+7' + phone[1:]
    elif phone.startswith('7'):
        phone = '+' + phone
    elif not phone.startswith('+7'):
        phone = '+7' + phone
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, service, date, time, status 
        FROM appointments 
        WHERE phone = ? 
        ORDER BY date DESC, time DESC
    """, (phone,))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        await update.message.reply_text("❌ Записей не найдено. Проверьте номер телефона.")
        return
    
    text = "📋 <b>Ваши записи:</b>\n\n"
    for app in appointments:
        status_icon = "✅" if app[4] == 'active' else "❌"
        text += (f"{status_icon} <b>ID:</b> #{app[0]}\n"
                f"   <b>Услуга:</b> {app[1]}\n"
                f"   <b>Дата:</b> {app[2]}\n"
                f"   <b>Время:</b> {app[3]}\n"
                f"   <b>Статус:</b> {'Активна' if app[4] == 'active' else 'Отменена'}\n\n")
    
    text += "💡 Для отмены записи используйте:\n<code>/cancel_booking ID_записи</code>"
    
    await update.message.reply_text(text, parse_mode='HTML')

# Команды для мастера
async def master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_phone = update.effective_user.phone_number or ""
    user_input = update.message.text.replace('/master', '').replace('/master_today', '').strip()
    
    # Проверяем, является ли пользователь мастером
    is_master = (user_phone and MASTER_PHONE in user_phone) or (user_input == MASTER_PHONE)
    
    if not is_master:
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
            SELECT id, service, time, name, phone 
            FROM appointments 
            WHERE date = ? AND status = 'active'
            ORDER BY time
        """, (today,))
        appointments = cursor.fetchall()
        
        if not appointments:
            await update.message.reply_text("📭 На сегодня записей нет.")
            conn.close()
            return
        
        text = f"📅 <b>Записи на сегодня ({today}):</b>\n\n"
        total = 0
        for app in appointments:
            price = extract_price(app[1])
            total += price
            text += (f"🕒 <b>{app[2]}</b> - {app[3]}\n"
                    f"   📱 {app[4]}\n"
                    f"   💇 {app[1]}\n"
                    f"   🆔 #{app[0]}\n\n")
        
        text += f"💰 <b>Итого за день: {total}₽</b>"
        
    else:
        # Все активные записи
        cursor.execute("""
            SELECT id, service, date, time, name, phone 
            FROM appointments 
            WHERE status = 'active' AND date >= date('now')
            ORDER BY date, time
        """)
        appointments = cursor.fetchall()
        
        if not appointments:
            await update.message.reply_text("📭 Активных записей нет.")
            conn.close()
            return
        
        text = "📋 <b>Все активные записи:</b>\n\n"
        current_date = None
        for app in appointments:
            if app[2] != current_date:
                current_date = app[2]
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][datetime.strptime(current_date, '%d.%m.%Y').weekday()]
                text += f"\n📅 <b>{current_date} ({weekday})</b>\n"
            
            text += (f"   🕒 <b>{app[3]}</b> - {app[4]}\n"
                    f"      📱 {app[5]}\n"
                    f"      💇 {app[1]}\n"
                    f"      🆔 #{app[0]}\n")
    
    conn.close()
    await update.message.reply_text(text, parse_mode='HTML')

def extract_price(service_text):
    """Извлекает цену из текста услуги"""
    match = re.search(r'(\d+)₽', service_text)
    return int(match.group(1)) if match else 0

# Отмена записи
async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Укажите ID записи для отмены:\n"
            "<code>/cancel_booking 123</code>\n\n"
            "📋 Чтобы узнать ID записи, используйте:\n"
            "<code>/my_bookings +79123456789</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        booking_id = int(args[0])
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        
        # Получаем информацию о записи
        cursor.execute("SELECT * FROM appointments WHERE id = ?", (booking_id,))
        appointment = cursor.fetchone()
        
        if not appointment:
            await update.message.reply_text("❌ Запись не найдена.")
            conn.close()
            return
        
        # Обновляем статус
        cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (booking_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Запись #{booking_id} отменена.\n\n"
            f"💇 Услуга: {appointment[1]}\n"
            f"📅 Дата: {appointment[2]}\n"
            f"🕒 Время: {appointment[3]}\n"
            f"👤 Клиент: {appointment[4]}"
        )
        
    except (ValueError, sqlite3.Error) as e:
        await update.message.reply_text("❌ Ошибка при отмене записи. Проверьте ID.")

# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('❌ Запись отменена', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Обработка ошибок
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик диалога записи
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            SERVICE: [CallbackQueryHandler(service_handler, pattern='^service_')],
            DATE: [CallbackQueryHandler(date_handler, pattern='^(date_|back_to_dates|cancel)$')],
            TIME: [CallbackQueryHandler(time_handler, pattern='^(time_|back_to_services|back_to_dates|cancel)$')],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            CONFIRM: [CallbackQueryHandler(confirm_handler, pattern='^confirm_')]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("services", show_services))
    application.add_handler(CommandHandler("contacts", contacts))
    application.add_handler(CommandHandler("my_bookings", my_bookings))
    application.add_handler(CommandHandler("master", master_command))
    application.add_handler(CommandHandler("master_today", master_command))
    application.add_handler(CommandHandler("cancel_booking", cancel_booking))
    application.add_handler(conv_handler)
    application.add_error_handler(error)
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
