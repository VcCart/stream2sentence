# stream2sentence.py
# -*- coding: utf-8 -*-
"""
Real-time processing and delivery of sentences from a continuous stream of characters or text chunks.
(Универсальная версия: поддержка стихов, обычного текста, плавная обработка, точные паузы)
"""

import functools
import logging
import re
from typing import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Concatenate,
    Iterable,
    Iterator,
    ParamSpec,
    List,
    Optional,
    Set,
    Tuple
)

import emoji

# --- Глобальные переменные состояния токенизатора ---
current_tokenizer = "stanza"
stanza_initialized = False
nltk_initialized = False
nlp = None # Для Stanza

# --- Категории знаков препинания ---
# Сильные разделители - почти всегда означают конец предложения (длинная пауза)
STRONG_DELIMITERS: Set[str] = {'.', '!', '?', '\n', '\u2026', '\u3002'}  # 🇷🇺 убрано тире из сильных разделителей — не конец предложения
# Слабые разделители - потенциальные границы внутри сложных предложений (короткая пауза)
WEAK_DELIMITERS: Set[str] = {',', ';', ':', '—'}  # 🇷🇺 тире теперь слабый разделитель (короткая пауза внутри фразы)
# Игнорируемые символы - на них паузу делать не нужно
IGNORED_DELIMITERS: Set[str] = {'"', "'", '(', ')', '[', ']', '{', '}', '«', '»', '\r', ' '}  # 🇷🇺 дефис '-' теперь не игнорируется
# Все фрагментные разделители (для подсчета слов и первоначальной проверки)
SENTENCE_FRAGMENT_DELIMITERS: Set[str] = STRONG_DELIMITERS | WEAK_DELIMITERS

# --- Функции инициализации токенизаторов ---

def initialize_nltk(debug: bool = False) -> None:
    """
    Initializes NLTK by downloading required data for sentence tokenization.
    """
    global nltk_initialized
    if nltk_initialized:
        return

    logging.info("Initializing NLTK Tokenizer")

    try:
        import nltk
        # Проверка наличия данных, загрузка при необходимости
        try:
            _ = nltk.data.find('tokenizers/punkt_tab')  # Обновлено: punkt_tab вместо punkt
        except LookupError:
            nltk.download('punkt_tab', quiet=not debug)  # Обновлено: punkt_tab
        nltk_initialized = True
    except Exception as e:
        print(f"Error initializing nltk tokenizer: {e}")
        nltk_initialized = False

def initialize_stanza(language: str = "ru", offline: bool = False) -> None:
    """
    Initializes Stanza by downloading required data for sentence tokenization.
    Оптимизировано для XTTS2 - использует только необходимые процессоры.
    """
    global nlp, stanza_initialized
    if stanza_initialized:
        return

    logging.info("Initializing Stanza Tokenizer")

    try:
        import stanza
        if not offline:
            stanza.download(language)
        # Оптимизировано для XTTS2 - только токенизация
        nlp = stanza.Pipeline(language, processors='tokenize', download_method=None)
        stanza_initialized = True
    except Exception as e:
        print(f"Error initializing stanza tokenizer: {e}")
        stanza_initialized = False

# --- Вспомогательные функции ---

def _remove_emojis(text: str) -> str:
    """
    Removes emojis from the input text.
    """
    return emoji.replace_emoji(text, "")

async def _generate_characters(
    generator: AsyncIterable[str], 
    log_characters: bool = False
) -> AsyncIterator[str]:
    """
    Generates individual characters from a text generator.
    """
    if log_characters:
        print("Stream: ", end="", flush=True)
    async for chunk in generator:
        for char in chunk:
            if log_characters:
                print(char, end="", flush=True)
            yield char
    if log_characters:
        print()

def _clean_text(
    text: str,
    cleanup_text_emojis: bool = False,
    strip_text: bool = True,
) -> str:
    """
    Cleans the text by removing emojis only.
    """
    if cleanup_text_emojis:
        text = _remove_emojis(text)
    if strip_text:
        text = text.strip()
    return text

def _is_likely_sentence_boundary(text: str, delimiter_pos: int, next_chars: str = "") -> bool:
    """
    Умная проверка - действительно ли это конец предложения для русского языка.
    Возвращает False для запятых в коротких словах и точек в аббревиатурах.
    """
    if delimiter_pos < 1:
        return False
    
    delimiter_char = text[delimiter_pos]
    
    # Для ЗАПЯТЫХ - проверяем длину фрагмента перед запятой
    if delimiter_char == ',':
        fragment_before = text[:delimiter_pos].strip()
        # Если перед запятой очень короткий фрагмент (меньше 4 символов) - скорее всего это не граница предложения
        if len(fragment_before) < 4:
            return False
        # Если перед запятой короткое слово (2-3 символа) - тоже пропускаем
        words = fragment_before.split()
        if words and len(words[-1]) <= 3:
            return False
    
    # Для ТОЧЕК - проверяем контекст на аббревиатуры
    elif delimiter_char == '.':
        # Ищем начало "слова" перед точкой
        word_start = delimiter_pos - 1
        while word_start >= 0 and (text[word_start].isalpha() or text[word_start] in {'-', '_'}):
            word_start -= 1
        
        word_before_dot = text[word_start + 1:delimiter_pos]
        
        # Признаки аббревиатуры:
        # - Очень короткое "слово" перед точкой (1-2 символа)
        # - Следующий символ - не пробел или тоже буква/точка
        if (len(word_before_dot) <= 2 and 
            (delimiter_pos + 1 < len(text)) and 
            (text[delimiter_pos + 1].isalnum() or text[delimiter_pos + 1] == '.')):
            return False  # Это аббревиатура, не граница предложения
    
    return True

def _tokenize_sentences(text: str, tokenize_sentences: Optional[Callable[[str], List[str]]] = None, 
                       poetic_mode: bool = False, preserve_line_breaks: bool = False) -> List[str]:
    """
    Tokenizes sentences from the input text with proper error handling.
    """
    global nlp, current_tokenizer
    try:
        if tokenize_sentences:
            sentences = tokenize_sentences(text)
        else:
            # Для поэтического режима - специальная обработка
            if poetic_mode:
                # В поэтическом режиме сохраняем структуру строк
                if preserve_line_breaks:
                    # Разбиваем по строкам, но не считаем их концами предложений
                    lines = text.split('\n')
                    sentences = [line for line in lines if line.strip()]
                else:
                    # Обычная токенизация, но с меньшей чувствительностью к \n
                    text = text.replace('\n', ' ')  # Заменяем переносы на пробелы
                    if current_tokenizer == "nltk":
                        import nltk
                        sentences = nltk.tokenize.sent_tokenize(text, language='russian')
                    elif current_tokenizer == "stanza":
                        import stanza
                        if nlp is None:
                            logging.warning("Stanza tokenizer not initialized, falling back to raw text.")
                            return [text]
                        doc = nlp(text)
                        sentences = [sentence.text for sentence in doc.sentences]
                    else:
                        raise ValueError(f"Unknown tokenizer: {current_tokenizer}")
            else:
                # Обычный режим
                if current_tokenizer == "nltk":
                    import nltk
                    sentences = nltk.tokenize.sent_tokenize(text, language='russian')
                elif current_tokenizer == "stanza":
                    import stanza
                    if nlp is None:
                        logging.warning("Stanza tokenizer not initialized, falling back to raw text.")
                        return [text]
                    doc = nlp(text)
                    sentences = [sentence.text for sentence in doc.sentences]
                else:
                    raise ValueError(f"Unknown tokenizer: {current_tokenizer}")
        
        # Интеллектуальное объединение коротких предложений (новое улучшение)
        combined_sentences = []
        temp_sentence = ""

        for sentence in sentences:
            if len(sentence) < 10:  # минимальная длина для объединения
                temp_sentence += sentence + " "
            else:
                if temp_sentence:
                    temp_sentence += sentence
                    combined_sentences.append(temp_sentence.strip())
                    temp_sentence = ""
                else:
                    combined_sentences.append(sentence.strip())

        # Если есть незавершенное объединение
        if temp_sentence:
            combined_sentences.append(temp_sentence.strip())

        # Используем объединенные предложения если они есть
        result = combined_sentences if combined_sentences and len(combined_sentences) < len(sentences) else sentences
        result = result if result else [text]
        return result
    except Exception as e:
        logging.warning(f"Tokenization error: {e}, returning raw text")
        return [text]

def init_tokenizer(tokenizer: str, language: str = "ru", offline: bool = False, debug: bool = False) -> None:
    """
    Initializes the sentence tokenizer.
    """
    global current_tokenizer
    if tokenizer == "nltk":
        initialize_nltk(debug)
    elif tokenizer == "stanza":
        initialize_stanza(language, offline=offline)
    else:
        logging.warning(f"Unknown tokenizer: {tokenizer}")

# --- Основная функция генерации предложений ---

async def generate_sentences_async(
    generator: AsyncIterable[str],  
    context_size: int = 15,
    context_size_look_overhead: int = 8,
    minimum_sentence_length: int = 12,  # 🇷🇺 УВЕЛИЧЕНО для избежания коротких фрагментов
    minimum_first_fragment_length: int = 8,  # 🇷🇺 УМЕНЬШЕНО для первого фрагмента
    quick_yield_single_sentence_fragment: bool = True,
    quick_yield_for_all_sentences: bool = False,
    quick_yield_every_fragment: bool = False,
    cleanup_text_emojis: bool = False,
    tokenize_sentences: Optional[Callable[[str], List[str]]] = None,
    tokenizer: str = "stanza",
    language: str = "ru",
    log_characters: bool = False,
    filter_first_non_alnum_characters: bool = True,
    force_first_fragment_after_words: int = 15,  # Увеличен
    debug: bool = False,
    # Параметры универсальности
    poetic_mode: bool = False,
    preserve_line_breaks: bool = False,
    adaptive_context: bool = True,
    smooth_short_fragments: bool = True,
    # Оптимизация для XTTS2
    max_buffer_size: int = 700,
    tokenization_interval: int = 6,  # Увеличен для избежания частых проверок
    strict_punctuation_mode: bool = True,
    min_chars_after_delimiter: int = 25,  # 🇷🇺 УВЕЛИЧЕНО для точности
    # Новые параметры (полезные улучшения)
    sentence_fragment_delimiters: str = ".?!;:,\n…)]}。—",  # Кастомизируемые разделители
    full_sentence_delimiters: str = ".?!\n…。—",  # Кастомизируемые полные разделители
    # Обратная совместимость
    cleanup_text_links: bool = False,
) -> AsyncIterator[str]:
    """
    Универсальная версия для XTTS2: поддержка стихов и прозы, плавная обработка.
    Оптимизирована для Stanza и реального времени. Паузы только на знаках препинания.
    """

    global current_tokenizer
    current_tokenizer = tokenizer
    init_tokenizer(current_tokenizer, language, debug)

    buffer = ""
    is_first_sentence = True
    word_count = 0
    last_delimiter_position = -1
    fragment_count = 0
    tokenization_counter = 0
    chars_since_last_strong_delim = 0
    # 🇷🇺 коэффициенты для длительности пауз в зависимости от типа знака препинания
    weak_pause_ratio = 0.6  # 🇷🇺 короткая пауза после запятых, точек с запятой, тире
    strong_pause_ratio = 1.0  # 🇷🇺 стандартная пауза после точки, восклицательного и вопросительного знака

    # Конвертируем строковые разделители в sets для более быстрой проверки
    sentence_fragment_delims_set = set(sentence_fragment_delimiters)
    full_sentence_delims_set = set(full_sentence_delimiters)

    # Adjust quick yield flags based on settings
    if quick_yield_every_fragment:
        quick_yield_for_all_sentences = True

    if quick_yield_for_all_sentences:
        quick_yield_single_sentence_fragment = True

    async for char in _generate_characters(generator, log_characters):

        if char:
            # Фильтрация начальных не-алфавитно-цифровых символов
            if len(buffer) == 0 and filter_first_non_alnum_characters:
                if not char.isalnum() and char not in {'(', '[', '«', '"', "'"}:
                    continue

            buffer += char
            buffer = buffer.lstrip()

            # Update word count and track delimiter distances
            if char.isspace() or char in sentence_fragment_delims_set:
                word_count += 1
                if char in full_sentence_delims_set:
                    chars_since_last_strong_delim = 0
                elif char not in IGNORED_DELIMITERS:
                    chars_since_last_strong_delim += 1
            else:
                chars_since_last_strong_delim += 1

            if debug:
                print(f"\033[36mDebug: Buffer size: {len(buffer)}, Words: {word_count}\033[0m")

            # --- Ограничение размера буфера для стабильности ---
            if len(buffer) > max_buffer_size:
                # Принудительно выдать часть буфера
                forced_text = buffer[:max_buffer_size//2]
                buffer = buffer[max_buffer_size//2:]
                yield_text = _clean_text(forced_text, cleanup_text_emojis)
                yield yield_text
                word_count = max(0, word_count - 6)
                tokenization_counter = 0
                chars_since_last_strong_delim = 0
                continue

            # --- Логика для первого фрагмента ---
            if (
                is_first_sentence
                and len(buffer) >= minimum_first_fragment_length
                and quick_yield_single_sentence_fragment
            ):
                # Улучшенные условия для первого фрагмента
                if (
                    buffer[-1] in sentence_fragment_delims_set
                    or char.isspace() and word_count >= force_first_fragment_after_words
                ):
                    # 🇷🇺 ФИЛЬТР: не выдавать очень короткие фрагменты с запятыми
                    if (buffer[-1] == ',' and len(buffer.strip()) < 6):
                        continue  # Пропускаем короткие фрагменты с запятыми
                    
                    if debug:
                        if buffer[-1] in sentence_fragment_delims_set:
                            print(f"\033[36mDebug: Yielding first fragment: \"{buffer}\" (delimiter)\033[0m")
                        else:
                            print(f"\033[36mDebug: Yielding first fragment: \"{buffer}\" (word limit)\033[0m")

                    yield_text = _clean_text(buffer, cleanup_text_emojis)
                    yield yield_text

                    buffer = ""
                    if not quick_yield_every_fragment:
                        is_first_sentence = False

                    word_count = 0
                    fragment_count += 1
                    tokenization_counter = 0
                    chars_since_last_strong_delim = 0
                    continue

            # Continue accumulating if buffer is too small
            if len(buffer) <= minimum_sentence_length + context_size:
                continue

            # Update last delimiter position if a new STRONG delimiter is found
            if char in full_sentence_delims_set:
                last_delimiter_position = len(buffer) - 1

            # --- УЛУЧШЕННАЯ ЛОГИКА ОБРАБОТКИ ---
            if len(buffer) > context_size:
                delimiter_char = buffer[-context_size]
                
                # В строгом режиме паузы только на знаках препинания
                if strict_punctuation_mode:
                    # Игнорируем не-разделители
                    if delimiter_char not in sentence_fragment_delims_set:
                        continue
                else:
                    # Игнорируем символы, на которых паузу делать не нужно
                    if delimiter_char in IGNORED_DELIMITERS:
                        continue
                
                # Только для сильных и слабых разделителей
                is_strong_delim = delimiter_char in full_sentence_delims_set
                is_weak_delim = delimiter_char in set(";:,")  # Ограниченные слабые разделители
                
                if is_strong_delim or is_weak_delim:
                    # Дополнительная проверка: после знака препинания должно быть достаточно текста
                    chars_after_delimiter = context_size - 1
                    if chars_after_delimiter < min_chars_after_delimiter:
                        continue  # Слишком мало текста после знака препинания
                    
                    # 🇷🇺 УМНАЯ ПРОВЕРКА ДЛЯ РУССКОГО ЯЗЫКА: фильтруем ложные границы
                    if not _is_likely_sentence_boundary(buffer, len(buffer) - context_size):
                        continue  # Пропускаем - это не настоящая граница предложения
                    
                    # Ограничиваем частоту токенизации для производительности
                    tokenization_counter += 1
                    # Для слабых разделителей проверяем реже, для сильных - чаще
                    if is_weak_delim:
                        check_interval = max(1, int(tokenization_interval * weak_pause_ratio))
                    elif is_strong_delim:
                        check_interval = int(tokenization_interval * strong_pause_ratio)
                    else:
                        check_interval = tokenization_interval
                    if tokenization_counter < check_interval:
                        continue
                    tokenization_counter = 0
                    
                    # Определяем "окно" вокруг позиции context_size
                    context_window_end_pos = len(buffer) - context_size - 1
                    context_window_start_pos = context_window_end_pos - context_size_look_overhead
                    if context_window_start_pos < 0:
                        context_window_start_pos = 0

                    # Вызываем токенизатор для проверки
                    sentences = _tokenize_sentences(buffer, tokenize_sentences, 
                                                  poetic_mode, preserve_line_breaks)

                    if debug:
                        print(f"\033[36mbuffer: \"{buffer}\"\033[0m")
                        print(f"\033[36mDelimiter: '{delimiter_char}' at pos {len(buffer)-context_size}\033[0m")
                        print(f"\033[36mSentences found: {len(sentences)}\033[0m")

                    # Улучшенная логика обработки результатов токенизации
                    if len(sentences) > 1:
                        # Проверяем общую длину всех предложений кроме последнего
                        total_length_except_last = sum(len(sentence) for sentence in sentences[:-1])
                        
                        if total_length_except_last >= minimum_sentence_length:
                            for sentence in sentences[:-1]:
                                # Только если предложение достаточно длинное
                                if len(sentence) >= minimum_sentence_length // 2:
                                    yield_text = _clean_text(sentence, cleanup_text_emojis)
                                    if debug:
                                        print(f"\033[36mDebug: Yielding validated sentence: \"{yield_text}\"\033[0m")
                                    yield yield_text
                                    word_count = 0

                            if quick_yield_for_all_sentences:
                                is_first_sentence = True

                            # Сохраняем пробелы в конце буфера (важное улучшение)
                            ends_with_space = buffer.endswith(" ")
                            buffer = sentences[-1]
                            if ends_with_space:
                                buffer += " "

                            # Reset counters
                            last_delimiter_position = -1 
                            word_count = 0
                            fragment_count += 1
                            chars_since_last_strong_delim = 0

    # --- Выдача остатка буфера в конце ---
    if buffer:
        sentences = _tokenize_sentences(buffer, tokenize_sentences, 
                                      poetic_mode, preserve_line_breaks)
        sentence_buffer = ""

        for sentence in sentences:
            sentence_buffer += sentence
            if len(sentence_buffer) < minimum_sentence_length:
                sentence_buffer += " "
                continue

            if debug:
                print(f"\033[36mDebug: Yielding final sentence(s): \"{sentence_buffer}\"\033[0m")
            yield_text = _clean_text(sentence_buffer, cleanup_text_emojis)
            yield yield_text
            sentence_buffer = ""

        if sentence_buffer:
            yield_text = _clean_text(sentence_buffer, cleanup_text_emojis)
            if debug:
                print(f"\033[36mDebug: Yielding remaining text: \"{yield_text}\"\033[0m")
            yield yield_text


# --- Синхронная обёртка ---

def _await_sync(f: Awaitable[str]) -> str:
    gen = f.__await__()
    try:
        next(gen)
        raise RuntimeError(f"{f} failed to be synchronous")
    except StopIteration as e:
        return e.value


def _async_iter_to_sync(f: AsyncIterator[str]) -> Iterator[str]:
    try:
        while True:
            yield _await_sync(f.__anext__())
    except StopAsyncIteration:
        return


P = ParamSpec("P")


def _dowrap(
    f: Callable[Concatenate[AsyncIterable[str], P], AsyncIterator[str]]
) -> Callable[Concatenate[Iterable[str], P], Iterator[str]]:
    @functools.wraps(f)
    def inner(generator: Iterable[str], *args: P.args, **kwargs: P.kwargs):
        # Обратная совместимость: игнорируем cleanup_text_links если передан
        kwargs.pop('cleanup_text_links', None)
        async def gen_wrap():
            for x in generator:
                yield x

        return _async_iter_to_sync(f(gen_wrap(), *args, **kwargs))

    return inner


generate_sentences = _dowrap(generate_sentences_async)
generate_sentences.__name__ = "generate_sentences"
generate_sentences.__qualname__ = "generate_sentences"
