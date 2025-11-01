# Stream2Sentence

Библиотека для обработки и выдачи предложений из непрерывного потока символов или текстовых фрагментов в реальном времени. Универсальная версия с поддержкой стихов, обычного текста, плавной обработкой и точными паузами.

## Особенности

- **Реальное время**: Генерация предложений из потокового текста с минимальной задержкой
- **Универсальность**: Поддержка как прозаического, так и поэтического текста
- **Умная токенизация**: Интеграция с Stanza и NLTK для точного определения границ предложений
- **Гибкая настройка**: Множество параметров для баланса между скоростью и точностью
- **Оптимизация для XTTS2**: Специальные настройки для синтеза речи
- **Поддержка русского языка**: Улучшенная обработка особенностей русского языка

## Установка

```bash
pip install stream2sentence
```

Для использования Stanza токенизатора (рекомендуется):
```bash
pip install stanza
```

Для использования NLTK токенизатора:
```bash
pip install nltk
```

## Быстрый старт

### Базовое использование

```python
from stream2sentence import generate_sentences

# Демонстрационный генератор текста
def text_generator():
    yield "Это первое предложение. А вот второе! И третье, "
    yield "которое продолжается. Завершающее предложение."

for sentence in generate_sentences(text_generator()):
    print(sentence)
```

Результат:
```
Это первое предложение.
А вот второе!
И третье, которое продолжается.
Завершающее предложение.
```

### Асинхронное использование

```python
import asyncio
from stream2sentence import generate_sentences_async

async def async_text_generator():
    yield "Асинхронная обработка "
    yield "текстового потока. "
    yield "Второе предложение!"
    
async def main():
    async for sentence in generate_sentences_async(async_text_generator()):
        print(sentence)

asyncio.run(main())
```

## Основные возможности

### Поэтический режим

```python
# Для обработки стихов с сохранением структуры строк
for sentence in generate_sentences(
    poem_generator,
    poetic_mode=True,
    preserve_line_breaks=True
):
    print(sentence)
```

### Быстрая выдача фрагментов

```python
# Для приложений синтеза речи с минимальной задержкой
for sentence in generate_sentences(
    generator,
    quick_yield_single_sentence_fragment=True,
    quick_yield_for_all_sentences=True
):
    synthesize_speech(sentence)  # Немедленная обработка
```

## Конфигурация

### Основные параметры

- `generator`: Входной генератор текста (синхронный или асинхронный)
- `context_size`: Размер контекста для обнаружения границ предложений (по умолчанию: 15)
- `minimum_sentence_length`: Минимальная длина предложения (по умолчанию: 12)
- `minimum_first_fragment_length`: Минимальная длина первого фрагмента (по умолчанию: 8)
- `tokenizer`: Выбор токенизатора ("stanza" или "nltk", по умолчанию: "stanza")
- `language`: Язык для токенизации (по умолчанию: "ru")

### Параметры производительности

- `quick_yield_single_sentence_fragment`: Быстрая выдача первого фрагмента
- `quick_yield_for_all_sentences`: Быстрая выдача всех предложений
- `max_buffer_size`: Максимальный размер буфера (по умолчанию: 700)
- `tokenization_interval`: Интервал токенизации (по умолчанию: 6)

### Специальные режимы

- `poetic_mode`: Режим для обработки поэзии
- `preserve_line_breaks`: Сохранение переносов строк
- `strict_punctuation_mode`: Строгий режим пауз только на знаках препинания
- `cleanup_text_emojis`: Удаление эмодзи из текста

## Примеры использования

### Интеграция с LLM для TTS

```python
from stream2sentence import generate_sentences

def llm_text_stream():
    # Имитация потока от языковой модели
    chunks = [
        "Привет! Как твои дела? ",
        "У меня всё отлично. ",
        "Сегодня прекрасная погода для прогулки."
    ]
    for chunk in chunks:
        yield chunk

# Использование в конвейере TTS
for sentence in generate_sentences(
    llm_text_stream(),
    quick_yield_single_sentence_fragment=True,
    tokenizer="stanza",
    language="ru"
):
    text_to_speech(sentence)  # Отправка на синтез речи
```

### Обработка потокового ввода

```python
import requests
from stream2sentence import generate_sentences_async

async def stream_from_api():
    response = requests.get('https://api.example.com/stream', stream=True)
    for line in response.iter_lines():
        if line:
            yield line.decode('utf-8')

async def process_stream():
    async for sentence in generate_sentences_async(
        stream_from_api(),
        cleanup_text_emojis=True,
        debug=True
    ):
        # Обработка каждого предложения
        await save_to_database(sentence)
```

## Инициализация токенизаторов

### Stanza (рекомендуется)

```python
from stream2sentence import init_tokenizer

init_tokenizer("stanza", language="ru", offline=False)
```

### NLTK

```python
from stream2sentence import init_tokenizer

init_tokenizer("nltk", debug=True)
```

## Типы разделителей

Библиотека использует интеллектуальную систему разделителей:

**Сильные разделители** (длинные паузы):
- `. ! ? \n … ?` - конец предложения

**Слабые разделители** (короткие паузы):
- `, ; : —` - границы внутри сложных предложений

**Игнорируемые символы** (без пауз):
- `" ' ( ) [ ] { } « »` - кавычки и скобки

## Особенности для русского языка

- Умное распознавание аббревиатур с точками
- Фильтрация ложных границ предложений в коротких фрагментах
- Специальная обработка запятых в коротких словах
- Оптимизированные паузы для естественного звучания

## Советы по использованию

1. **Для TTS приложений**: Используйте `quick_yield_single_sentence_fragment=True`
2. **Для точной обработки**: Выбирайте Stanza токенизатор
3. **Для поэзии**: Включайте `poetic_mode` и `preserve_line_breaks`
4. **Для отладки**: Используйте `debug=True` для подробного вывода

## Устранение неполадок

### Проблемы с токенизацией

```python
# Принудительная инициализация токенизатора
init_tokenizer("stanza", language="ru", offline=False, debug=True)

# Резервный вариант - использование raw mode
for sentence in generate_sentences(generator, tokenizer="nltk"):
    process(sentence)
```

### Оптимизация производительности

```python
# Уменьшение размера буфера для низколатентных приложений
for sentence in generate_sentences(
    generator,
    max_buffer_size=300,
    tokenization_interval=3
):
    real_time_processing(sentence)
```

## Лицензия

Проект распространяется под лицензией MIT.

---

Разработано для обеспечения плавного и естественного преобразования текста в речь в реальном времени с поддержкой особенностей русского языка.
