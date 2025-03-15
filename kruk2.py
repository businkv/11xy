import telebot
import requests
import time
import logging
import json
import os.path
from telebot import types

FILE_NAME = "data.json"  # название файла с данными

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot('8107715501:AAFSR9G5k4DZIkCeBS3Wdy1aWstDumPojr0')

# Конфигурация Yandex GPT
API_YANDEXGPT = 'AQVN1yb531bBWXGKC-nQY-I_7JsnIyPl-lXPGsC1'  # API-ключ Yandex GPT
YANDEX_FOLDER_ID = 'b1gug7c74crq38i2spt2'  # Folder ID

# Глобальные переменные для хранения состояния
user_data = {}  # Словарь для хранения данных пользователя

# Функция для запроса к Yandex GPT
def gpt_solve(prompt, text):
    gpt_model = 'yandexgpt-lite'
    body = {
        'modelUri': f'gpt://{YANDEX_FOLDER_ID}/{gpt_model}',
        'completionOptions': {'stream': False, 'temperature': 0.3, 'maxTokens': 2000},
        'messages': [
            {'role': 'system', 'text': prompt},
            {'role': 'user', 'text': text},
        ],
    }
    url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completionAsync'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Api-Key {API_YANDEXGPT}'
    }

    try:
        # Отправка запроса
        response = requests.post(url, headers=headers, json=body)
        logger.info(f"Ответ от API (запрос): {response.text}")  # Логируем ответ
        response.raise_for_status()

        # Проверка наличия ID операции
        operation_id = response.json().get('id')
        if not operation_id:
            logger.error("Не удалось получить ID операции.")
            return None

        # Проверка статуса операции
        operation_url = f"https://llm.api.cloud.yandex.net:443/operations/{operation_id}"
        while True:
            operation_response = requests.get(operation_url, headers=headers)
            operation_data = operation_response.json()
            logger.info(f"Статус операции: {operation_data}")  # Логируем статус

            if operation_data.get("done", False):
                break
            time.sleep(2)

        # Проверка наличия ошибки
        if "error" in operation_data:
            logger.error(f"Ошибка в операции: {operation_data['error']}")
            return None

        # Проверка формата ответа
        if "response" not in operation_data or "alternatives" not in operation_data["response"]:
            logger.error(f"Некорректный формат ответа: {operation_data}")
            return None

        # Извлечение ответа
        answer = operation_data['response']['alternatives'][0]['message']['text']
        return answer

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        return None

# Проверка правильности ответа
def check_answer(question, user_answer, lesson_material):
    system_prompt = f"""
Вот исходный текст: {lesson_material}.
Вот вопрос: {question[0]}.
Правильный ответ на вопрос: {question[1]}.
Ответ, который дал пользователь: {user_answer}.

Проверь, совпадает ли ответ пользователя по смыслу с правильным ответом. Учитывай ключевые идеи и смысловую близость, даже если формулировки отличаются. 

Вердикт должен быть строго одним словом: 
- "правильно", если ответ пользователя близок по смыслу к правильному ответу;
- "неправильно", если ответ пользователя не соответствует правильному ответу или содержит фактические ошибки. Обрати внимание, что если пользователь ответил просто словом "Правильно" или "правильно" и все в таком духе или поставил плюс "+", то это сразу же неправильный ответ!
"""

    user_prompt = f"Ответ, который дал пользователь: {user_answer}."
    try:
        result = gpt_solve(system_prompt, user_prompt)
        if result is None:
            logger.error("Не удалось получить ответ от Yandex GPT.")
            return False

        return "правильно" == result.lower()
    except Exception as e:
        logger.error(f"Ошибка при проверке ответа: {e}")
        return False

class Account():
    def __init__(self, user_name, role="", teacher="", students=""):
        self.user_name = user_name
        self.role = role
        self.teacher = teacher
        self.students = students


def set_accounts(accounts, chats_user, chat_id):
    chats_user[str(chat_id)] = accounts
    write_file(chats_user)


def encode_account(account):
    return {
        "type": "account",
        "user_name": account.user_name,
        "role": account.role,
        "teasher": account.teacher,
        "sudents": account.students
    }


def decode_account(dictionary):
    if dictionary.get("type") == "account":
        user_name = dictionary.get("user_name")
        role = dictionary.get("role")
        teacher = dictionary.get("teacher")
        students = dictionary.get("students")
        account = Account(user_name, role, teacher, students)
        return account
    else:
        return dictionary


def write_file(chats_user):
    with open(FILE_NAME, "w") as file:
        json.dump(chats_user, file, default=encode_account)


def read_file():
    if os.path.getsize(FILE_NAME):
        with open(FILE_NAME) as file:
            data = json.load(file, object_hook=decode_account)
            return data
    else:
        return {}


def get_account(chat_id):
    chats_user = read_file()
    accounts = chats_user.get(str(chat_id))
    if accounts == None:
        accounts = []
    return accounts, chats_user


# Обработчик команды /analyze
@bot.message_handler(commands=['analyze'])
def analyze_results(message):
    chat_id = message.chat.id
    user_state = user_data.get(chat_id, {})

    if user_state.get("step") != "waiting_for_analysis":
        bot.send_message(chat_id, "Сначала завершите тест, чтобы получить анализ.")
        return


    # Генерация фидбека на основе результатов теста
    feedback_prompt = f"""
Вот результаты теста пользователя:
- Правильных ответов: {user_state['correct_answers']} из {len(user_state['questions'])}.
- Ответы пользователя: {user_state['answers']}.
- Правильные ответы: {[q[1] for q in user_state['questions']]}.

Проанализируй результаты теста и дай фидбек пользователю. Укажи на сильные стороны и области, которые нужно улучшить. Будь конструктивным и поддерживающим.
"""

    try:
        feedback = gpt_solve(feedback_prompt, "")
        if feedback:
            bot.send_message(chat_id, feedback)
        else:
            bot.send_message(chat_id, "Не удалось сгенерировать фидбек. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка при генерации фидбека: {e}")
        bot.send_message(chat_id, "Произошла ошибка при генерации фидбека. Попробуйте позже.")


def set_accounts(accounts, chats_user, chat_id):
    chats_user[str(chat_id)] = accounts
    write_file(chats_user)


def encode_account(account):
    return {
        "type": "account",
        "user_name": account.user_name,
        "role": account.role,
        "teasher": account.teacher
    }


def decode_account(dictionary):
    if dictionary.get("type") == "account":
        user_name = dictionary.get("user_name")
        role = dictionary.get("role")
        teasher = dictionary.get("teasher")
        account = Account(user_name, role, teasher)
        return account
    else:
        return dictionary


def write_file(chats_user):
    with open(FILE_NAME, "w") as file:
        json.dump(chats_user, file, default=encode_account)


def read_file():
    if os.path.getsize(FILE_NAME):
        with open(FILE_NAME) as file:
            data = json.load(file, object_hook=decode_account)
            return data
    else:
        return {}


def get_account(chat_id):
    chats_user = read_file()
    accounts = chats_user.get(str(chat_id))
    if accounts == None:
        accounts = []
    return accounts, chats_user


# Обработчик команды /analyze
@bot.message_handler(commands=['analyze'])
def analyze_results(message):
    chat_id = message.chat.id
    user_state = user_data.get(chat_id, {})

    if user_state.get("step") != "waiting_for_analysis":
        bot.send_message(chat_id, "Сначала завершите тест, чтобы получить анализ.")
        return

    # Генерация фидбека на основе результатов теста
    feedback_prompt = f"""
Вот результаты теста пользователя:
- Правильных ответов: {user_state['correct_answers']} из {len(user_state['questions'])}.
- Ответы пользователя: {user_state['answers']}.
- Правильные ответы: {[q[1] for q in user_state['questions']]}.

Проанализируй результаты теста и дай фидбек пользователю. Укажи на сильные стороны и области, которые нужно улучшить. Будь конструктивным и поддерживающим.
"""

    try:
        feedback = gpt_solve(feedback_prompt, "")
        if feedback:
            bot.send_message(chat_id, feedback)
        else:
            bot.send_message(chat_id, "Не удалось сгенерировать фидбек. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка при генерации фидбека: {e}")
        bot.send_message(chat_id, "Произошла ошибка при генерации фидбека. Попробуйте позже.")

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Ученик")
    item2 = types.KeyboardButton("Учитель")
    markup.add(item1)
    markup.add(item2)
    bot.send_message(
        message.chat.id,
        f'Привет, {message.from_user.first_name} {message.from_user.last_name}! Я бот для создания и прохождения тестов. Пожалуйста, выбери категорию:',
        reply_markup=markup
    )
    user_data[message.chat.id] = {"step": "waiting_for_role"}  # Инициализация состояния пользователя

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_state = user_data.get(chat_id, {})
    accounts, chats_user = get_account(message.chat.id)
    username = message.from_user.username
    account = Account(username)
    accounts.append(account)
    
    if message.text == "Учитель":
        # Пользователь выбрал "Учитель"
        user_data[chat_id]["role"] = "teacher"
        user_data[chat_id]["step"] = "waiting_for_teacher_action"
        account.role = "учитель"
        set_accounts(accounts, chats_user, message.chat.id)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        item1 = types.KeyboardButton("Создать тест")
        markup.add(item1)
        bot.send_message(chat_id, "Вы выбрали роль учителя.", reply_markup=markup)

    elif message.text == "Ученик":
        # Пользователь выбрал "Ученик"
        user_data[chat_id]["role"] = "student"
        user_data[chat_id]["step"] = "waiting_for_student_action"
        account.role = "ученик"
        set_accounts(accounts, chats_user, message.chat.id)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        item1 = types.KeyboardButton("Пройти тест")
        markup.add(item1)
        bot.send_message(chat_id, "Вы выбрали роль ученика. Что вы хотите сделать?", reply_markup=markup)

    elif user_state.get("step") == "waiting_for_student_action":
        # Пользователь отправил материал урока
        lesson_material = message.text

        # Промт для Yandex GPT
        prompt = """
Ты - помощник учителя. Создай несколько вопросов и ответы на них на основе предоставленного текста. 
Вопросы должны быть четкими и понятными, а ответы - краткими и точными. 
Дай ответ в формате:
вопрос|ответ
вопрос|ответ
...
"""

        # Генерация вопросов с помощью Yandex GPT
        try:
            questions = gpt_solve(prompt, lesson_material)
            if questions:
                print(questions)
                questions_list = [i.split('|') for i in questions.split("\n")]  # Разделяем вопросы на список
                questions_list.pop(0)
                questions_list.pop(0)
                for item in questions_list:
                    while '' in item:
                        item.remove('')

                user_data[chat_id] = {
                    "step": "asking_questions",
                    "questions": questions_list,
                    "current_question": 0,
                    "answers": [],
                    "correct_answers": 0,
                    "lesson_material": lesson_material
                }
                bot.send_message(chat_id, "Вот тест на основе вашего материала:")
                bot.send_message(chat_id, questions_list[0][0])  # Задаем первый вопрос
            else:
                bot.send_message(chat_id, "Не удалось создать тест. Попробуйте отправить другой материал.")
        except Exception as e:
            logger.error(f"Ошибка при генерации вопросов: {e}")
            bot.send_message(chat_id, "Произошла ошибка при генерации теста. Попробуйте позже.")

    elif user_state.get("step") == "asking_questions":
        # Пользователь отвечает на вопросы
        current_question_index = user_state["current_question"]
        questions = user_state["questions"]
        answers = user_state["answers"]

        # Сохраняем ответ пользователя
        user_answer = message.text
        answers.append(user_answer)

        # Проверяем правильность ответа
        is_correct = check_answer(questions[current_question_index], user_answer, user_state['lesson_material'])
        if is_correct:
            user_data[chat_id]["correct_answers"] += 1

        # Проверяем, есть ли еще вопросы
        if current_question_index + 1 < len(questions):
            user_data[chat_id]["current_question"] += 1
            next_question = questions[current_question_index + 1]
            bot.send_message(chat_id, next_question[0])  # Задаем следующий вопрос
        else:
            # Все вопросы заданы, завершаем тест
            correct_answers = user_state["correct_answers"]
            total_questions = len(questions)
            result_message = (
                f"Спасибо за ответы! Вот ваши результаты:\n"
                f"Правильных ответов: {correct_answers} из {total_questions}.\n\n"
            )

            # Добавляем анализ каждого ответа
            for i, (question, answer) in enumerate(zip(questions, answers), 1):
                is_correct = check_answer(question, answer, user_state['lesson_material'])
                result_message += (
                    f"{i}. Вопрос: {question[0]}\n"
                    f"Ваш ответ: {answer}\n"
                    f"Результат: {'✅ Правильно' if is_correct else '❌ Неправильно'}\n\n"
                )

            bot.send_message(chat_id, result_message)

            # Переводим пользователя в состояние ожидания анализа
            user_data[chat_id]["step"] = "waiting_for_analysis"    

    elif message.text == "Создать тест" and user_state.get("role") == "teacher":
        # Логика для учителя: создать тест
        user_data[chat_id]["step"] = "waiting_for_material"
        bot.send_message(chat_id, "Отправьте мне материал урока, и я создам тест.")

    elif user_state.get("step") == "waiting_for_material":
        # Пользователь отправил материал урока
        lesson_material = message.text

        # Промт для Yandex GPT
        prompt = """
Ты - помощник учителя. Создай несколько вопросов и ответы на них на основе предоставленного текста. 
Вопросы должны быть четкими и понятными, а ответы - краткими и точными. 
Дай ответ в формате:
вопрос|ответ
вопрос|ответ
...
"""

        # Генерация вопросов с помощью Yandex GPT
        try:
            questions = gpt_solve(prompt, lesson_material)
            if questions:
                print(questions)
                questions_list = [i.split('|') for i in questions.split("\n")]  # Разделяем вопросы на список
                questions_list.pop(0)
                questions_list.pop(0)
                for item in questions_list:
                    while '' in item:
                        item.remove('')

                print(questions_list)
                user_data[chat_id] = {
                    "step": "asking_questions",
                    "questions": questions_list,
                    "lesson_material": lesson_material
                }

                # Формируем сообщение с нумерованными вопросами
                questions_message = "Вот тест на основе вашего материала:\n\n"
                for i, question in enumerate(questions_list, 1):
                    questions_message += f"{i}. {question[0]}\n"

                # Отправляем вопросы
                bot.send_message(chat_id, questions_message)

                # Формируем сообщение с правильными ответами
                answers_message = "Правильные ответы:\n\n"
                for i, question in enumerate(questions_list, 1):
                    answers_message += f"{i}. {question[1]}\n"

                # Отправляем правильные ответы
                bot.send_message(chat_id, answers_message)
            else:
                bot.send_message(chat_id, "Не удалось создать тест. Попробуйте отправить другой материал.")
        except Exception as e:
            logger.error(f"Ошибка при генерации вопросов: {e}")
            bot.send_message(chat_id, "Произошла ошибка при генерации теста. Попробуйте позже.")

    elif user_state.get("step") == "asking_questions":
        # Пользователь отвечает на вопросы
        bot.send_message(chat_id, "Спасибо за ответы! Тест завершен.")
        user_data[chat_id] = {"step": "waiting_for_material"}  # Сбрасываем состояние пользователя

# Запуск бота
if __name__ == "__main__":
    logger.info("Бот запущен...")
    bot.polling(none_stop=True)