import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import sqlite3
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Определение состояний разговора
SERVICE, DATE, TIME, NAME, PHONE = range(5)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

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
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в бот для записи на прием!\n\n"
        "📅 Для записи на прием введите /book\n"
        "📋 Для просмотра ваших записей введите /my_bookings\n"
        "❌ Для отмены записи введите /cancel_booking"
    )

# Начало процесса записи
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите услугу:",
        reply_markup=ReplyKeyboardMarkup([
            ['💇 Стрижка', '💅 Маникюр'],
            ['💆 Массаж', '🧖 SPA']
        ], one_time_keyboard=True)
    )
    return SERVICE

# Выбор услуги
async def service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['service'] = update.message.text
    await update.message.reply_text(
        "Введите дату приема (формат: ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardRemove()
    )
    return DATE

# Ввод даты
async def date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_str = update.message.text
        date_obj = datetime.strptime(date_str, '%d.%m.%Y').date()
        
        if date_obj < datetime.now().date():
            await update.message.reply_text("❌ Неверная дата! Введите будущую дату:")
            return DATE
            
        context.user_data['date'] = date_str
        await update.message.reply_text("Введите время приема (формат: ЧЧ:ММ):")
        return TIME
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Введите дату в формате ДД.ММ.ГГГГ:")
        return DATE

# Ввод времени
async def time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_str = update.message.text
        datetime.strptime(time_str, '%H:%M')
        context.user_data['time'] = time_str
        await update.message.reply_text("Введите ваше имя:")
        return NAME
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Введите время в формате ЧЧ:ММ:")
        return TIME

# Ввод имени
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Введите ваш номер телефона:")
    return PHONE

# Ввод телефона и сохранение записи
async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    
    # Сохранение в базу данных
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO appointments (service, date, time, name, phone) VALUES (?, ?, ?, ?, ?)",
                   (context.user_data['service'], context.user_data['date'],
                    context.user_data['time'], context.user_data['name'],
                    context.user_data['phone']))
    conn.commit()
    conn.close()
    
    # Отправка подтверждения
    await update.message.reply_text(
        f"✅ Запись успешно создана!\n\n"
        f"📋 Детали записи:\n"
        f"• Услуга: {context.user_data['service']}\n"
        f"• Дата: {context.user_data['date']}\n"
        f"• Время: {context.user_data['time']}\n"
        f"• Имя: {context.user_data['name']}\n"
        f"• Телефон: {context.user_data['phone']}\n\n"
        f"Мы ждем вас! 🎉"
    )
    return ConversationHandler.END

# Просмотр своих записей
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_phone = update.message.text.replace('/my_bookings', '').strip()
    
    if not user_phone:
        await update.message.reply_text("📞 Для просмотра записей введите номер телефона после команды:\n/my_bookings 79123456789")
        return
    
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM appointments WHERE phone = ? ORDER BY date, time", (user_phone,))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        await update.message.reply_text("❌ Записей не найдено. Проверьте номер телефона.")
        return
    
    text = "📋 Ваши записи:\n\n"
    for app in appointments:
        text += (f"ID: {app[0]}\n"
                f"Услуга: {app[1]}\n"
                f"Дата: {app[2]}\n"
                f"Время: {app[3]}\n"
                f"Имя: {app[4]}\n"
                f"Телефон: {app[5]}\n\n")
    
    await update.message.reply_text(text)

# Отмена записи
async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите ID записи для отмены:\n/cancel_booking 1")
        return
    
    try:
        booking_id = int(args[0])
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appointments WHERE id = ?", (booking_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Запись #{booking_id} успешно отменена!")
        
    except (ValueError, sqlite3.Error):
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
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, service)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, date)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, time)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("my_bookings", my_bookings))
    application.add_handler(CommandHandler("cancel_booking", cancel_booking))
    application.add_handler(conv_handler)
    application.add_error_handler(error)
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()