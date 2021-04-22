from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from telegram import Bot
from telegram import Update
from telegram.ext import CallbackContext
from telegram.utils.request import Request
from flea_app.models import Profile, Post
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          ConversationHandler)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
import logging
import datetime

chanel = settings.CHANEL_TEST

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TYPE, PHOTO, PRICE, DESCRIPTION = range(4)


def update_or_create_user(f):
    def wrapper(update: Update, context: CallbackContext, **kwargs):
        p, created = Profile.objects.get_or_create(
            external_id=update.message.chat_id,
            defaults={
                'username': update.message.from_user.username,
            }
        )
        return f(update, context, profile=p, created=created)

    return wrapper


@update_or_create_user
def post_disable_list(update, context, **kwargs):
    profile = kwargs['profile']
    posts = Post.objects.filter(profile=profile)
    keyboard = []
    prefix = "BUTTON_CANCEL_"
    for post in posts:
        if post.status == Post.Status.APPROVED:
            keyboard.append(
                [InlineKeyboardButton("Отключить: " + post.text[:20] + '..', callback_data=prefix + str(post.pk))])

    if not len(keyboard):
        context.bot.sendMessage(chat_id=profile.external_id, text="У вас нет активных постов для отключения")
    else:
        markup = InlineKeyboardMarkup(keyboard)
        context.bot.sendMessage(chat_id=profile.external_id, text="Выберите пост для отключения:", reply_markup=markup)
    logger.info("Пользователь @%s: запросил список постов для деактивации", profile.username)



def post_disable(context, post):
    post.status = Post.Status.SOLD
    post.save()
    new_text = text_from_post(post)
    if post.image_file_id:
        context.bot.editMessageCaption(chat_id=chanel, message_id=int(post.external_id), caption=new_text)
    else:
        context.bot.editMessageText(chat_id=chanel, message_id=int(post.external_id), text=new_text)


def text_from_post(post):
    separator = '\n_______________________________\n'
    text = post.type_p + separator
    if post.status != Post.Status.SOLD:
        text += '🍏 #Активно' + separator
    else:
        text += '🍎 #Продано' + separator
    text += post.text + separator
    if post.price:
        text += 'Цена: ' + post.price + separator
    text += 'Писать: @' + post.profile.username
    return text


# Кнопки клавиатуры для админов
BUTTON_APPROVE = "BUTTON_APPROVE"
BUTTON_COMMERCIAL = "BUTTON_COMMERCIAL"
BUTTON_COMMERCIAL_NO_TRANSACTION = "BUTTON_COMMERCIAL_NO_TRANSACTION"
BUTTON_DECLINE = "BUTTON_DECLINE"
# Кнопки клавиатуры для пользователей
BUTTON_PAYED = "BUTTON_PAYED"

KEYBOARD_TITLES = {
    BUTTON_APPROVE: "Опубликовать",
    BUTTON_COMMERCIAL: "Комерческое",
    BUTTON_DECLINE: "Отклонить",
    BUTTON_PAYED: "Оплачено",
}


def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_APPROVE], callback_data=BUTTON_APPROVE), ],
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_COMMERCIAL], callback_data=BUTTON_COMMERCIAL), ],
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_DECLINE], callback_data=BUTTON_DECLINE), ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_commercial_keyboard():
    keyboard = [
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_PAYED], callback_data=BUTTON_PAYED), ],
    ]
    return InlineKeyboardMarkup(keyboard)


def approve_post(context, post):
    if post.status != Post.Status.APPROVED:
        post.reviewed_at = timezone.now()
        post.status = Post.Status.APPROVED
        post.save()

        text = text_from_post(post)
        if post.image_file_id:
            message = context.bot.sendPhoto(chat_id=chanel, photo=post.image_file_id,
                                            caption=text)
        else:
            message = context.bot.sendMessage(chat_id=chanel, text=text)
        post.external_id = message.message_id
        post.save()
        context.bot.sendMessage(chat_id=post.profile.external_id,
                                text="Ваш пост опубликован\n Спасибо 🙏 что воспользовались сервисом")
        context.bot.forwardMessage(chat_id=post.profile.external_id, from_chat_id=chanel,
                                   message_id=post.external_id)


def commercial_post(context, post):
    post.status = Post.Status.WAIT_MONEY
    post.reviewed_at = timezone.now()
    post.save()

    post_id = str(post.pk)
    text = """
Здравствуйте, ваш пост распознан как, коммерческий
За размещение рекламного обьявления взымается плата в размере
100 грн
Пожалауйста, нажмите кнопку "Оплачено", после совершения транзакции.

Реквизиты:
4149 4991 4336 5912
    
После, проверки пост появится в ленте
    """
    text = text + '\nID: ' + post_id
    context.bot.sendMessage(chat_id=post.profile.external_id, text=text, reply_markup=get_commercial_keyboard())


def decline_post(context, post):
    if post.status == Post.Status.ON_REVIEW or post.status == Post.Status.WAIT_MONEY:
        reason = 'Здравствуйте, наша система классификации, с помощью нейросети определила ваш пост как неприемлемый\n'
        reason += 'Попытайтесь еще 🍀'
        post.status = Post.Status.DECLINE
        post.reviewed_at = timezone.now()
        post.save()
        context.bot.sendMessage(chat_id=post.profile.external_id, text=reason)


def edit_post_for_admin(update, decision):
    query = update.callback_query
    current_text = update.effective_message.text
    current_caption = update.effective_message.caption

    if current_text:
        text = current_text
        with_image = False
    if current_caption:
        text = current_caption
        with_image = True

    split = text.split('\n')
    _id = int(split[0])
    post = Post.objects.get(pk=_id)
    text = text + '\n' + decision
    if not with_image:
        query.edit_message_text(
            text=text
        )
    else:
        query.edit_message_caption(
            caption=text
        )
    return post


def get_admin_keyboard_after_payed():
    keyboard = [
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_APPROVE], callback_data=BUTTON_APPROVE), ],
        [InlineKeyboardButton(KEYBOARD_TITLES[BUTTON_DECLINE], callback_data=BUTTON_DECLINE), ],
    ]
    return InlineKeyboardMarkup(keyboard)


def send_post_to_admins_after_payed(update, context):
    current_text = update.effective_message.text
    current_caption = update.effective_message.caption

    if current_text:
        text = current_text
    if current_caption:
        text = current_caption

    split = text.split('\n')
    _id = int(split[-1][4:])
    post = Post.objects.get(pk=_id)
    notify_admins(post, context, get_admin_keyboard_after_payed())
    return post


def keyboard_handler(update, context):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_message.chat_id
    profile = Profile.objects.get(external_id=chat_id)

    if profile.is_admin:
        if data == BUTTON_APPROVE:
            post = edit_post_for_admin(update, 'ОДОБРЕНО')
            logger.info("Администратор @%s: одобрил пост: %s", profile.username, str(post.pk))
            if post.status == Post.Status.ON_REVIEW:
                approve_post(context, post)
        elif data == BUTTON_COMMERCIAL:
            post = edit_post_for_admin(update, 'ОТПРАВЛЕН ЗАПРОС ОПЛАТЫ')
            logger.info("Администратор @%s: запросил оплату на пост: %s", profile.username, str(post.pk))
            if post.status == Post.Status.ON_REVIEW:
                commercial_post(context, post)
        elif data == BUTTON_DECLINE:
            post = edit_post_for_admin(update, 'ОТКЛОНЕНО')
            logger.info("Администратор @%s: отклонил пост: %s", profile.username, str(post.pk))
            if post.status == Post.Status.ON_REVIEW:
                decline_post(context, post)
    if data == BUTTON_PAYED:
        context.bot.sendMessage(chat_id=chat_id, text="Спасибо, после подтверждения пост появится в ленте\nЧто бы создать новый пост отправьте /start",
                                disable_notification=True)
        post = send_post_to_admins_after_payed(update, context)
        logger.info("Пользователь @%s: сообщает что оплатил пост: %s", profile.username, str(post.pk))
    if data[:len('BUTTON_CANCEL_')] == 'BUTTON_CANCEL_':
        id_ = int(data[len('BUTTON_CANCEL_'):])
        post = Post.objects.get(pk=id_)
        post_disable(context, post)
        logger.info("Пользователь @%s: деактивирует пост: %s", profile.username, str(post.pk))

        context.bot.sendMessage(chat_id=chat_id, text="Ваш пост успешно деактивирован")


def notify_admins(post, context, keyboard=get_admin_keyboard()):
    admins = Profile.objects.filter(is_admin=True)
    text = text_from_post(post)
    text = str(post.pk) + '\n' + text
    for admin in admins:
        if post.image_file_id:
            context.bot.sendPhoto(chat_id=admin.external_id, photo=post.image_file_id,
                                  caption=text, reply_markup=keyboard)
        else:   
            context.bot.sendMessage(chat_id=admin.external_id, text=text, reply_markup=keyboard)
        logger.info("Оповещен администратор @%s: о посте: %s", admin.username, str(post.pk))


@update_or_create_user
def post_create(update, context, **kwargs):
    reply_keyboard = [['Купить 🛒', 'Продать 💰', 'Другое 🎱']]
    profile = kwargs['profile']

    update.message.reply_text(
        'Привет! Это бот "Барахолка Олександрівки" Он поможет тебе создать пост.\n'
        'Создание пройдет в три этапа\n'
        '1) Фото\n'
        '2) Цена\n'
        '3) Описание\n'
        'Отправьте /cancel что бы прекратить создание поста.\n\n'
        'Выбери вариант: ',

        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))

    return TYPE


@update_or_create_user
def post_type(update, context, **kwargs):
    user = update.message.from_user
    profile = kwargs['profile']
    type_ = update.message.text[:-2]
    if type_ == 'Купить':
        type_ = '#Куплю'
    elif type_ == 'Продать':
        type_ = '#Продам'
    else:
        type_ = '#Другое'
    post = Post(
        profile=profile,
        type_p=type_,
        status=Post.Status.ON_CREATE
    )
    post.save()
    logger.info("Пользователь @%s: начинает создавать пост с типом: %s", user.username, update.message.text)
    update.message.reply_text('Хорошо! Пожалуйста пришли мне фото для поста\n'
                              'или /skip если фото не нужно',
                              reply_markup=ReplyKeyboardRemove())

    return PHOTO


@update_or_create_user
def photo(update, context, **kwargs):
    user = update.message.from_user
    profile = kwargs['profile']
    post = Post.objects.filter(status=Post.Status.ON_CREATE, profile=profile).order_by('created_at')[0]
    photo_file = update.message.photo[-1].get_file()
    post.image_file_id = photo_file.file_id
    post.save()
    logger.info("Сохранено фото от @%s: post id #%i", user.username, post.pk)
    update.message.reply_text('Отлично! Теперь пришли мне желаемую цену, '
                              'или /skip если в цене нет необходимости')

    return PRICE


@update_or_create_user
def skip_photo(update, context, **kwargs):
    user = update.message.from_user
    logger.info("Пользователь @%s не прислал фото", user.username)
    update.message.reply_text('Пост будет оформлен без фото.\nТеперь пришли мне желаемую цену, '
                              'или /skip что бы пропустить этот этап.')

    return PRICE


@update_or_create_user
def price(update, context, **kwargs):
    user = update.message.from_user
    profile = kwargs['profile']

    if update.message.text == '/cancel':
        return cancel(update, context, **kwargs)
    else:
        post = Post.objects.filter(status=Post.Status.ON_CREATE, profile=profile).order_by('created_at')[0]
        post.price = update.message.text
        post.save()
    logger.info("Указана цена %s от пользовтаеля @%s", update.message.text, user.username)
    update.message.reply_text('Цена сохранена\n'
                              'Теперь последний этап, пришли мне описание')

    return DESCRIPTION


@update_or_create_user
def skip_price(update, context, **kwargs):
    user = update.message.from_user
    logger.info("Пользователь @%s не прислал цену.", user.username)
    update.message.reply_text('Пост будет оформлен без указания цены. '
                              'Теперь последний этап, пришли мне описание')

    return DESCRIPTION


@update_or_create_user
def description(update, context, **kwargs):
    user = update.message.from_user
    profile = kwargs['profile']
    post = Post.objects.filter(status=Post.Status.ON_CREATE, profile=profile).order_by('created_at')[0]
    post.text = update.message.text
    post.status = Post.Status.ON_REVIEW
    post.save()
    logger.info("Добавлено описание от пользователя @%s: %s", user.username, update.message.text)
    update.message.reply_text('Спасибо! После этапа модерации пост появится в ленте')
    notify_admins(post, context)
    return ConversationHandler.END


@update_or_create_user
def cancel(update, context, **kwargs):
    user = update.message.from_user
    logger.info("Пользователь @%s отменил создание поста.", user.username)
    profile = kwargs['profile']
    try:
        post = Post.objects.filter(status=Post.Status.ON_CREATE, profile=profile).order_by('created_at')[0]
        post.delete()
    except IndexError:
        logger.info("Попытка удаления поста от пользователя @%s, объект еще не был создан", user.username)
    update.message.reply_text('Пока! Операция отменена',
                              reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END


def log_errors(f):
    def inner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            error_message = f'Произошла ошибка: {e}'
            print(error_message)
            raise e

    return inner


@log_errors
def do_echo(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    p, created = Profile.objects.get_or_create(
        external_id=chat_id,
        defaults={
            'username': update.message.from_user.username,
        }
    )

    reply_text = "Ваш ID {}\n\n{}".format(chat_id, text)
    update.message.reply_text(
        text=reply_text
    )


@update_or_create_user
def do_start(update: Update, context: CallbackContext, **kwargs):
    profile = kwargs['profile']
    reply_keyboard = [['Создать пост', 'Отключить пост']]
    update.message.reply_text(
        text=f"Вас приветствует Барахолка БОТ\n",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )


class Command(BaseCommand):
    help = 'Телеграм бот'

    def handle(self, *args, **options):
        request = Request(
            connect_timeout=0.5,
            read_timeout=1.0,
            con_pool_size=8,
        )
        bot = Bot(
            request=request,
            token=settings.TOKEN
        )
        print(bot.get_me())

        updater = Updater(
            bot=bot,
            use_context=True
        )

        conversation_create_post_handler = ConversationHandler(
            entry_points=[MessageHandler(Filters.regex('^(Создать пост)$'), post_create)],

            states={
                TYPE: [MessageHandler(Filters.regex('^(Купить 🛒|Продать 💰|Другое 🎱)$'), post_type)],

                PHOTO: [MessageHandler(Filters.photo, photo),
                        CommandHandler('skip', skip_photo)],

                PRICE: [CommandHandler('skip', skip_price),
                        MessageHandler(Filters.text, price)],

                DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, description)]
            },

            fallbacks=[CommandHandler('cancel', cancel)]
        )

        start_handler = CommandHandler("start", do_start)
        updater.dispatcher.add_handler(start_handler)

        disable_massage_handler = MessageHandler(Filters.regex('^(Отключить пост)$'), post_disable_list)
        # disable_command_handler = CommandHandler('disable', post_disable)
        admin_buttons_handler = CallbackQueryHandler(keyboard_handler)

        updater.dispatcher.add_handler(admin_buttons_handler)
        updater.dispatcher.add_handler(conversation_create_post_handler)
        updater.dispatcher.add_handler(disable_massage_handler)
        # updater.dispatcher.add_handler(disable_command_handler)
        # message_handler = MessageHandler(Filters.text, do_echo)

        # updater.dispatcher.add_handler(message_handler)

        updater.start_polling()
        updater.idle()
