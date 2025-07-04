from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import os

# Твой токен Telegram-бота
TOKEN = '7554259067:AAFWKzMf77iM4U0k9Rsc5zyEj6qH5CcqgDY'

# Путь к PDF-файлу
PDF_PATH = 'guide.pdf'

def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("✅ Я оплатил", callback_data='paid')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = (
        "📘 Добро пожаловать в @GetWowGuideBot!\n\n"
        "Вы получите PDF-гайд:\n"
        "*Как создавать WOW-контент для Telegram и Reels*\n\n"
        "💸 Стоимость: *199₽*\n"
        "💳 Оплата на карту: *5321 5400 1045 1967*\n\n"
        "После оплаты нажмите кнопку ниже 👇"
    )
    update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == 'paid':
        if os.path.exists(PDF_PATH):
            query.message.reply_document(open(PDF_PATH, 'rb'), filename='WOW_Guide.pdf')
            query.message.reply_text("✅ Спасибо за оплату! Вот ваш гайд.")
        else:
            query.message.reply_text("⚠️ PDF-файл не найден. Пожалуйста, свяжитесь с админом.")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CallbackQueryHandler(button))

    updater.start_polling()
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    updater.idle()

if __name__ == '__main__':
    main()