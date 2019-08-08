#!/usr/bin/python3
# -*- coding: utf-8 -*-
import argparse
import mongomock
import os
import random
import telebot
import time
import uuid

from datetime import datetime
from flask import Flask, request
from pymongo import MongoClient


TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

server = Flask(__name__)
TELEBOT_URL = 'telegram/'
BASE_URL = 'https://wizard-of-music.herokuapp.com/'

MONGO_URL = os.environ.get('MONGODB_URI')
if MONGO_URL is not None:
    mongo_client = MongoClient(MONGO_URL)
    mongo_db = mongo_client.get_default_database()
else:
    mongo_client = mongomock.MongoClient()
    mongo_db = mongo_client.db

# user_id, username, allow_notifications, current_role, current_state, counterparty, game_id
mongo_users = mongo_db.get_collection('users')
# event, sender, receiver, text, sender_role, game_id, timestamp, message_id
mongo_game_logs = mongo_db.get_collection('game_logs')
# user_id, from_user, text, timestamp, message_id
mongo_messages = mongo_db.get_collection('messages')

PROCESSED_MESSAGES = set()


@server.route("/" + TELEBOT_URL)
def web_hook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEBOT_URL + TOKEN)
    return "!", 200


@server.route("/wakeup/")
def wake_up():
    web_hook()
    return "Маам, ну ещё пять минуточек!", 200


@server.route('/' + TELEBOT_URL + TOKEN, methods=['POST'])
def get_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@bot.message_handler(commands=['logs'])
def get_game_logs(m):
    if MONGO_URL is None:
        result = '\n'.join([str(row) for row in mongo_game_logs.find({})])
        bot.send_message(m.chat.id, result or 'logs are empty so far')
    else:
        bot.send_message(m.shat.id, "На проде логи нельзя посмотреть из бота.")


def render_markup(suggests=None, max_columns=3, initial_ratio=2):
    if suggests is None or len(suggests) == 0:
        return telebot.types.ReplyKeyboardRemove(selective=False)
    markup = telebot.types.ReplyKeyboardMarkup(row_width=max(1, min(max_columns, int(len(suggests) / initial_ratio))))
    markup.add(*suggests)
    return markup


def text_is_like(text, pattern):
    def preprocess(s):
        return s.lower().strip()
    return preprocess(text) in {preprocess(p) for p in pattern}


SUGGEST_SUBSCRIBE = 'Получать уведомления'
SUGGEST_UNSUBSCRIBE = 'Не получать уведомления'
SUGGEST_START_GAME = 'Начать игру'
SUGGEST_NOT_START_GAME = 'Не начинать игру'
SUGGEST_END_GAME = 'Завершить игру'

INITIAL_SELLER_SUGGESTS = [
    "Привет! Хотите купить подписку?",
    "Я заметила, что вы ещё не подписаны на Яндекс Музыку, хотите подписаться?",
    "Здравствуйте! У вас, наверное, уже есть подписка Яндекс.Плюс?",
]

INITIAL_BUYER_SUGGESTS = [
    "Здравствуйте! Сколько стоит подписка на Яндекс.Музыку?",
    "Привет! Где мне бесплатно можно музыку послушать?",
    "Добрый день! Мне нужна помощь в выборе музыкального сервиса.",
    "Расскажите, пожалуйста, что такое Яндекс.Плюс.",
]


STATE_ACTIVE = 'active'
STATE_INACTIVE = 'inactive'
STATE_IN_GAME = 'in_game'
STATE_FEEDBACK_DEAL = 'feedback_deal'
STATE_FEEDBACK_TERMS = 'feedback_terms'
STATE_FEEDBACK_WHY_NOT = 'feedback_why_not'
STATE_FEEDBACK_LIKE = 'feedback_like'

STATES_GAME = {STATE_IN_GAME}
STATES_FEEDBACK = {STATE_FEEDBACK_DEAL, STATE_FEEDBACK_LIKE, STATE_FEEDBACK_TERMS, STATE_FEEDBACK_WHY_NOT}
STATES_OUTSIDE = {STATE_ACTIVE, STATE_INACTIVE}

ROLE_BUYER = 'buyer'
ROLE_SELLER = 'seller'

ROLES_DICT = {ROLE_BUYER: 'потенциальный покупатель', ROLE_SELLER: 'продавец'}


WELCOME_TEXT = '<i>Привет! Я бот для игры в продажу подписки на Яндекс.Музыку.' \
               '\nВы будете выступать в роли покупателя или продавца (каждый раз это выбирается случайно).' \
               '\nНажмите "{}", если вы хотите начать игру прямо сейчас.' \
               '\nНажмите "{}", если вы хотите получать уведомления о желающих начать игру.' \
               '\nЧтобы проще было понимать, в игре ли вы в текущий момент, все сообщения от меня ' \
               'вы будете получать курсивом, как сейчас.</i>' \
               '\nА все сообщения от своего контрагента - прямым шрифтом, как теперь.' \
               '\n<i>Удачного торга!</i>'.format(SUGGEST_START_GAME, SUGGEST_SUBSCRIBE)

INTRO_BUYER = '<i>Игра началась! Вы - потенциальный ПОКУПАТЕЛЬ подписки на Яндекс.Музыку. ' \
              '\nВаша задача - выяснить, нужна ли вам подписка, и, если нужна, купить подешевле.' \
              '\n\n Я буду иногда давать вам кнопки-подсказки, но лучше пишите от себя.' \
              '\nУспешного торга!</i>'


INTRO_SELLER = '<i>Игра началась! Вы - ПРОДАВЕЦ подписки на Яндекс.Музыку. ' \
               '\nВаша задача - убедить покупателя, что ему/ей очень нужна подписка, и продать её подороже.' \
               '\n\nКакие есть подписки в реальности (для справки): ' \
               '\n - Нативная на месяц с коротким триалом (1 мес) - 169 ₽ - https://plus.yandex.ru ' \
               '\n - Нативная на год - 1690 ₽  - https://music.yandex.ru/pay' \
               '\n - Семейная на месяц - 299 ₽ - https://music.yandex.ru/family-plus' \
               '\n - Нативная КиноПоиск + Амедиатека (на месяц) - 649 ₽ - https://www.kinopoisk.ru/mykp ' \
               '\n\n Я буду иногда давать вам кнопки-подсказки, но лучше пишите от себя.' \
               '\n Успешного торга!</i>'

ROLES_INTRO_DICT = {ROLE_BUYER: INTRO_BUYER, ROLE_SELLER: INTRO_SELLER}

ROLES_INITIAL_SUGGESTS_DICT = {ROLE_BUYER: INITIAL_BUYER_SUGGESTS, ROLE_SELLER: INITIAL_SELLER_SUGGESTS}

ALL_CONTENT_TYPES = ['document', 'text', 'photo', 'audio', 'video',  'location', 'contact', 'sticker']

YES = ['Да', 'Удалось']
NO = ['Нет', 'Не удалось']
YES_NO_SUGGESTS = [YES[0], NO[0]]


def get_reply_markup_for_id(user_id):
    user_object = mongo_users.find_one({'user_id': user_id})
    return render_markup_for_user_object(user_object)


def get_suggests_for_user_object(user_object):
    if user_object.get('allow_notifications'):
        subscription_suggest = SUGGEST_UNSUBSCRIBE
    else:
        subscription_suggest = SUGGEST_SUBSCRIBE
    if user_object.get('current_state') == STATE_INACTIVE:
        game_suggest = SUGGEST_START_GAME
    elif user_object.get('current_state') == STATE_ACTIVE:
        game_suggest = SUGGEST_NOT_START_GAME
    else:
        game_suggest = SUGGEST_END_GAME
    return [subscription_suggest, game_suggest]


def shuffled(some_list):
    items = some_list[:]
    random.shuffle(items)
    return items


def render_markup_for_user_object(user_object):
    if user_object is None:
        return render_markup([])
    return render_markup(get_suggests_for_user_object(user_object))


def find_subscribed_users():
    user_ids = []
    user_objects = list(mongo_users.find({'allow_notifications': True, 'current_state': STATE_ACTIVE})) \
        + list(mongo_users.find({'allow_notifications': True, 'current_state': STATE_INACTIVE}))
    for uo in user_objects:
        user_ids.append(uo['user_id'])
    random.shuffle(user_ids)
    return user_ids


def send_text_to_user(user_id, text, reply_markup=None):
    if reply_markup is None:
        reply_markup = get_reply_markup_for_id(user_id)
    result = bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode='html')
    mongo_messages.insert_one({
        'user_id': user_id,
        'from_user': False,
        'text': text,
        'timestamp': datetime.utcnow(),
        'message_id': result.message_id
    })
    time.sleep(0.3)


@bot.message_handler(func=lambda message: True, content_types=ALL_CONTENT_TYPES)
def process_message(msg):
    if msg.message_id in PROCESSED_MESSAGES:
        return
    PROCESSED_MESSAGES.add(msg.message_id)
    bot.send_chat_action(msg.chat.id, 'typing')

    if msg.chat.type != "private":
        bot.reply_to(msg, "Я работаю только в приватных чатах. Удалите меня отсюда и напишите мне в личку!")
        return

    text = msg.text
    user_id = msg.from_user.id
    username = msg.from_user.username or 'Anonymous'

    mongo_messages.insert_one({
        'user_id': user_id,
        'from_user': True,
        'text': text,
        'timestamp': datetime.utcnow(),
        'message_id': msg.message_id
    })
    print("got message: '{}' from user {} ({})".format(text, user_id, username))

    user_object = mongo_users.find_one({'user_id': user_id})
    # todo: turn it into a class instead
    # todo: update userame, if it changes
    user_filter = {'user_id': user_id}

    if user_object is None:
        mongo_users.insert_one(
            {
                'user_id': user_id,
                'username': username,
                'allow_notifications': False,
                'current_state': STATE_INACTIVE,
                'current_role': None,
                'counterparty': None,
                'game_id': None
            }
        )
        send_text_to_user(
            user_id, WELCOME_TEXT, reply_markup=render_markup([SUGGEST_SUBSCRIBE, SUGGEST_START_GAME])
        )
        print("new user initialized")
        return
    print(user_object)

    current_state = user_object.get('current_state')
    current_role = user_object.get('current_role')
    current_role_name = ROLES_DICT.get(current_role, 'undefined')
    counterparty = user_object.get('counterparty')
    game_id = user_object.get('game_id')

    def add_game_log(log_event, log_text, log_sender_role=None):
        if log_sender_role is None:
            log_sender_role = current_role
        print('add game log: event "{}", text "{}", role "{}"'.format(log_event, log_text, log_sender_role))
        mongo_game_logs.insert_one({
            'event': log_event,
            'sender': user_id,
            'receiver': counterparty,
            'text': log_text,
            'sender_role': log_sender_role,
            'game_id': game_id,
            'timestamp': datetime.now(),
            'message_id': msg.message_id
        })

    subscription_suggest, game_suggest = get_suggests_for_user_object(user_object)
    default_markup = render_markup([subscription_suggest, game_suggest])

    if not text:
        send_text_to_user(
            user_id,
            '<i>Я пока не поддерживаю стикеры, фото и т.п.\nПожалуйста, пользуйтесь текстом и смайликами \U0001F642</i>',  # noqa
            reply_markup=default_markup)
        print("class: no text detected")
    elif text == SUGGEST_SUBSCRIBE:
        if user_object.get('allow_notifications'):
            send_text_to_user(
                user_id, '<i>Вы уже и так подписаны на обновления о новых игроках!</i>', reply_markup=default_markup,
            )
            print("class: subscribe, but already subscribed")
        else:
            mongo_users.update_one(user_filter, {'$set': {'allow_notifications': True}})
            send_text_to_user(
                user_id, '<i>Теперь вы подписаны на обновления о новых игроках!</i>',
                reply_markup=render_markup([SUGGEST_UNSUBSCRIBE, game_suggest])
            )
            print("class: subscribe successfully")
    elif text == SUGGEST_UNSUBSCRIBE:
        if not user_object.get('allow_notifications'):
            send_text_to_user(
                user_id, '<i>Вы уже и так отписаны от обновлений о новых игроках!</i>', reply_markup=default_markup
            )
            print("class: unsubscribe, but already unsubscribed")
        else:
            mongo_users.update_one(user_filter, {'$set': {'allow_notifications': False}})
            send_text_to_user(
                user_id, '<i>Теперь вы отписаны от обновлений о новых игроках.</i>',
                reply_markup=render_markup([SUGGEST_SUBSCRIBE, game_suggest])
            )
            print("class: unsubscribe successfully")
    elif text == SUGGEST_START_GAME and current_state in STATES_OUTSIDE:
        vacants = list(mongo_users.find({'current_state': STATE_ACTIVE}))
        random.shuffle(vacants)
        if len(vacants) > 0:
            counterparty = vacants[0]['user_id']
            game_id = str(uuid.uuid4())
            if random.random() < 0.5:
                new_role = ROLE_SELLER
                new_counterparty_role = ROLE_BUYER
            else:
                new_role = ROLE_BUYER
                new_counterparty_role = ROLE_SELLER
            mongo_users.update_one(
                user_filter,
                {'$set': {'current_state': STATE_IN_GAME, 'current_role': new_role, 'counterparty': counterparty, 'game_id': game_id}}
            )
            mongo_users.update_one(
                {'user_id': counterparty},
                {'$set': {'current_state': STATE_IN_GAME, 'current_role': new_counterparty_role, 'counterparty': user_id, 'game_id': game_id}}
            )
            add_game_log(log_event='game_start', log_text=None, log_sender_role=new_role)
            send_text_to_user(
                user_id, ROLES_INTRO_DICT[new_role],
                reply_markup=render_markup(shuffled(ROLES_INITIAL_SUGGESTS_DICT[new_role]))
            )
            send_text_to_user(
                counterparty,
                ROLES_INTRO_DICT[new_counterparty_role],
                reply_markup=render_markup(shuffled(ROLES_INITIAL_SUGGESTS_DICT[new_counterparty_role]))
            )
            print("class: start new game successfully")
        else:
            if current_state != STATE_ACTIVE:
                mongo_users.update_one(user_filter, {'$set': {'current_state': STATE_ACTIVE}})
            for other_user_id in find_subscribed_users():
                if other_user_id != user_id:
                    send_text_to_user(other_user_id, '<i>Кто-то готов к новой игре! Вы можете присоединиться!</i>')
            send_text_to_user(
                user_id,
                '<i>Сейчас нет свободных игроков. Игра начнётся, как только другой игрок будет готов.'
                '\nЕсли вы не хотите начинать игру, как только другой игрок появится, нажмите "{}"</i>'.format(
                    SUGGEST_NOT_START_GAME
                ),
                reply_markup=render_markup([subscription_suggest, SUGGEST_NOT_START_GAME]),
            )
            print("class: tried to start new game, but has no counterparty")
    elif text == SUGGEST_START_GAME and current_state == STATE_IN_GAME:
        send_text_to_user(
            user_id, '<i>Вы и так уже в игре! Ваша роль - {}</i>'.format(current_role_name),
            reply_markup=default_markup
        )
        print("class: tried to start new game, but already in a game")
    elif text == SUGGEST_END_GAME and current_state in STATES_OUTSIDE:
        send_text_to_user(
            user_id,
            '<i>Вы уже и так не играете. Нажмите "{}", чтобы не получать приглашения в следующие игры</i>'.format(
                SUGGEST_UNSUBSCRIBE
            ),
            reply_markup=default_markup
        )
        print("class: tried to end a game, but already not in a game")
    elif text == SUGGEST_END_GAME and current_state == STATE_IN_GAME:
        add_game_log(log_event='game_end', log_text=None)
        the_update = {'$set': {'current_state': STATE_FEEDBACK_DEAL}}
        mongo_users.update_one(user_filter, the_update)
        mongo_users.update_one({'user_id': counterparty}, the_update)
        send_text_to_user(
            user_id,
            '<i>Окей, вы завершили игру. Спасибо вам за неё!\nВам удалось договориться о сделке?</i>',
            reply_markup=render_markup(YES_NO_SUGGESTS)
        )
        send_text_to_user(
            counterparty,
            '<i>Ваш контрагент завершил игру. Спасибо вам за неё!\nВам удалось договориться о сделке?</i>',
            reply_markup=render_markup(YES_NO_SUGGESTS)
        )
        print("class: game ended successfully; ask whether it was successful")
    elif current_state == STATE_FEEDBACK_DEAL:
        if text_is_like(text, YES):
            add_game_log(log_event='feedback_deal', log_text='YES')
            mongo_users.update_one(user_filter, {'$set': {'current_state': STATE_FEEDBACK_TERMS}})
            send_text_to_user(
                user_id,
                '<i>Отлично! Пожалуйста, кратко опишите условия сделки '
                '(на какой цене вы сошлись; какие особые условия, если они есть).'
                '\nВажно: надо уложиться в одно сообщение.</i>',
                reply_markup=render_markup([])
            )
            print('class: collected a positive deal feedback')
        elif text_is_like(text, NO):
            add_game_log(log_event='feedback_deal', log_text='NO')
            mongo_users.update_one(user_filter, {'$set': {'current_state': STATE_FEEDBACK_WHY_NOT}})
            send_text_to_user(
                user_id,
                '<i>Как жаль! Пожалуйста, расскажите вкратце (в одном сообщении), почему сделка не состоялась?</i>',
                # noqa
                reply_markup=render_markup([])
            )
            print('class: collected a negative deal feedback')
        else:
            send_text_to_user(
                user_id,
                '<i>Простите, но я вас не понял. Договорились ли вы?\nПожалуйста, ответьте просто "Да" или "Нет".</i>',
                reply_markup=render_markup(YES_NO_SUGGESTS)
            )
            print('class: could not collect the deal feedback; reask')
    elif current_state in {STATE_FEEDBACK_TERMS, STATE_FEEDBACK_WHY_NOT}:
        if current_state == STATE_FEEDBACK_TERMS:
            add_game_log(log_event='feedback_terms', log_text=text)
        elif current_state == STATE_FEEDBACK_WHY_NOT:
            add_game_log(log_event='feedback_why_not', log_text=text)
        mongo_users.update_one(user_filter, {'$set': {'current_state': STATE_FEEDBACK_LIKE}})
        send_text_to_user(
            user_id,
            '<i>Понятно. Последний вопрос: насколько вам понравился этот разговор, '
            'по шкале от 1 (было ужасно) до 5 (просто огонь)?</i>',
            # noqa
            reply_markup=render_markup(['1', '2', '3', '4', '5'], max_columns=5)
        )
        print('class: terms/whynot feedback succesfully collected; ask for the like/dislike feedback')
    elif current_state == STATE_FEEDBACK_LIKE:
        add_game_log(log_event='feedback_like', log_text=text)
        mongo_users.update_one(
            user_filter, {'$set': {'current_state': STATE_INACTIVE, 'counterparty': None, 'game_id': None, 'current_role': None}}
        )
        send_text_to_user(
            user_id,
            '<i>Ага, понятно.\nБольшое спасибо вам за игру и обратную связь! Приходите ещё \U0001F60A</i>',
            reply_markup=render_markup([subscription_suggest, SUGGEST_START_GAME])
        )
        print('class: Like feedback succesfully collected; the round ended')
    elif text == SUGGEST_NOT_START_GAME and current_state == STATE_IN_GAME:
        send_text_to_user(
            user_id,
            '<i>Поздно! Вы уже в игре, ваша роль - {}.'
            '\nПопробуйте пройти её до конца, а когда завершите, нажмите "{}"</i>'.format(
                current_role_name,
                SUGGEST_END_GAME
            ),
            reply_markup=default_markup
        )
        print("class: tried not to start game, but already in a game")
    elif text == SUGGEST_NOT_START_GAME and current_state == STATE_INACTIVE:
        send_text_to_user(
            user_id,
            '<i>Вы и так не начинаете игру. '
            '\nПока вы сами не нажмёте "{}", игра не начнётся.'
            '\nЕсли вы не хотите получать уведомления о новых игроках, готовых к игре, нажмите "{}"</i>'.format(
                SUGGEST_START_GAME,
                SUGGEST_UNSUBSCRIBE
            ),
            reply_markup=default_markup
        )
        print("class: tried not to start a game, but already inactive")
    elif text == SUGGEST_NOT_START_GAME and current_state == STATE_ACTIVE:
        mongo_users.update_one(user_filter, {'$set': {'current_state': STATE_INACTIVE}})
        send_text_to_user(
            user_id,
            '<i>Хорошо, не будем начинать игру '
            '\nНажмите, "{}", когда снова будете готовы начать игру.'
            '\nЕсли вы не хотите получать уведомления о новых игроках, готовых к игре, нажмите "{}"</i>'.format(
                SUGGEST_START_GAME,
                SUGGEST_UNSUBSCRIBE
            ),
            reply_markup=render_markup([subscription_suggest, SUGGEST_START_GAME])
        )
        print("class: successfully decided not to start a game")
    elif current_state == STATE_IN_GAME:
        add_game_log(log_text=text, log_event='text')
        send_text_to_user(counterparty, text)
        print("class: some random text within a game; sent to the counterparty")
    else:
        # todo: болталка, вопросы, и всё такое
        send_text_to_user(user_id, WELCOME_TEXT, reply_markup=default_markup)
        print("class: some random text outside a game")


def main():
    parser = argparse.ArgumentParser(description='Run the bot')
    parser.add_argument('--poll', action='store_true')

    args = parser.parse_args()
    if args.poll:
        bot.remove_webhook()
        bot.polling()
    else:
        web_hook()
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    main()
