# Payment Service

Асинхронный сервис процессинга платежей. Принимает запрос на оплату, обрабатывает его через эмуляцию платёжного шлюза и уведомляет клиента о результате через webhook.

## Стек

- FastAPI, Pydantic v2
- SQLAlchemy 2.0 (async), PostgreSQL, Alembic
- RabbitMQ, FastStream
- Docker, docker-compose

## Запуск

```bash
docker compose up --build
```

Поднимаются четыре сервиса: `postgres`, `rabbitmq`, `api`, `consumer`. Миграции применяются автоматически при старте `api`.

| Что | Адрес |
|---|---|
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 (`guest` / `guest`) |

API-ключ по умолчанию — `secret-api-key`. Свой ключ задаётся переменной окружения `API_KEY`:

```bash
API_KEY=my-key docker compose up --build
```

Остановка с удалением данных:

```bash
docker compose down -v
```

## API

Все запросы требуют заголовок `X-API-Key`. Без него или с неверным ключом сервис отвечает `401`.

### Создание платежа

`POST /api/v1/payments`

Заголовок `Idempotency-Key` обязателен.

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: order-1" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Order 1",
    "metadata": {"order_id": 1},
    "webhook_url": "https://example.com/webhook"
  }'
```

Ответ `202 Accepted`:

```json
{
  "payment_id": "72d04251-4e0c-4849-b3ea-aced3b97e54b",
  "status": "pending",
  "created_at": "2026-10-02T10:50:20.561206Z"
}
```

| Поле | Описание |
|---|---|
| `amount` | сумма больше нуля, не более двух знаков после запятой |
| `currency` | `RUB`, `USD` или `EUR` |
| `description` | описание платежа |
| `metadata` | произвольный JSON-объект, необязательное поле |
| `webhook_url` | URL для уведомления о результате |

### Получение платежа

`GET /api/v1/payments/{payment_id}`

```bash
curl http://localhost:8000/api/v1/payments/72d04251-4e0c-4849-b3ea-aced3b97e54b \
  -H "X-API-Key: secret-api-key"
```

Ответ `200 OK`:

```json
{
  "payment_id": "72d04251-4e0c-4849-b3ea-aced3b97e54b",
  "amount": "100.50",
  "currency": "RUB",
  "description": "Order 1",
  "metadata": {"order_id": 1},
  "status": "succeeded",
  "idempotency_key": "order-1",
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-10-02T10:50:20.561206Z",
  "processed_at": "2026-10-02T10:50:24.980645Z"
}
```

Если платежа нет — `404`.

### Webhook

После обработки сервис отправляет `POST` на `webhook_url`:

```json
{
  "payment_id": "72d04251-4e0c-4849-b3ea-aced3b97e54b",
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "2026-10-02T10:50:24.980645Z"
}
```

Доставка считается успешной при ответе `2xx`.

Адрес `https://example.com/webhook` из примера на `POST` отвечает ошибкой, поэтому на нём видна работа retry и DLQ. Чтобы увидеть доставленный webhook, укажите в `webhook_url` адрес, принимающий `POST`, например с сервиса https://webhook.site.

## Как это работает

```
POST /payments ──> payments + outbox (одна транзакция)
                        │
                 outbox publisher
                        │
              exchange "payments" ──> queue "payments.new" ──> consumer ──> webhook
                                              │
                                   после 3 неудачных попыток
                                              │
                          exchange "payments.dlx" ──> queue "payments.dlq"
```

1. `api` в одной транзакции сохраняет платёж со статусом `pending` и событие в таблицу `outbox`.
2. Фоновая задача в `api` раз в секунду читает неотправленные события, публикует их в очередь `payments.new` и отмечает время публикации.
3. `consumer` получает сообщение, эмулирует обработку в шлюзе (2–5 секунд, 90% успех, 10% ошибка), сохраняет статус `succeeded` или `failed` и отправляет webhook.

### Outbox

Платёж и событие записываются атомарно, поэтому событие не теряется, даже если RabbitMQ недоступен в момент создания платежа: оно останется в `outbox` и будет опубликовано, когда брокер вернётся.

Событие может быть опубликовано повторно, если сервис упадёт между публикацией и фиксацией отметки. Это безопасно: consumer проводит платёж только в статусе `pending`.

### Идемпотентность

На `idempotency_key` стоит уникальный индекс. Повторный запрос с тем же ключом не создаёт новый платёж, а возвращает уже существующий.

### Retry и Dead Letter Queue

Обработка сообщения выполняется до 3 раз с экспоненциальной задержкой между попытками: 1 и 2 секунды. Ошибкой считается любой сбой обработки, включая недоставленный webhook.

После третьей неудачи сообщение отклоняется и через обменник `payments.dlx` попадает в очередь `payments.dlq`.

При повторной попытке шлюз заново не вызывается, если статус платежа уже сохранён, — повторяется только отправка webhook.

Статус `failed` — это результат платежа, а не ошибка обработки: он сохраняется, webhook отправляется, повторов нет.

Посмотреть очереди:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

## Принятые решения

- Публикация событий из outbox выполняется фоновой задачей внутри сервиса `api`, отдельного сервиса для неё нет.
- Повторный запрос с тем же `Idempotency-Key` возвращает существующий платёж с кодом `202`, тело запроса при этом не сравнивается.
- 3 попытки относятся к обработке сообщения целиком, а не только к отправке webhook.
- Consumer обрабатывает не более 10 сообщений одновременно.

## Тесты

Нужны Python 3.12 и запущенный Docker: интеграционные тесты поднимают PostgreSQL через testcontainers и применяют к нему миграции.

```bash
pip install -r requirements-dev.txt
pytest
```

Только unit-тесты, без Docker:

```bash
pytest -m "not integration"
```

- `tests/unit` — сервисы на фейковых репозиториях, отправка webhook через `httpx.MockTransport`, retry в consumer через `TestRabbitBroker`;
- `tests/integration` — API, outbox relay и обработка платежа на реальной базе, включая параллельные запросы с одним `Idempotency-Key` и параллельную обработку одного платежа.

## Структура проекта

```
app/
  core/           настройки из переменных окружения
  domain/         статусы, валюты, данные нового платежа, доменные исключения
  db/             модели, сессия, Unit of Work
  repositories/   доступ к таблицам payments и outbox
  services/
    payments.py   создание и получение платежа, идемпотентность
    processing.py обработка платежа в consumer
    gateway.py    эмуляция платёжного шлюза
    webhooks.py   отправка webhook
  api/            эндпоинты, проверка API-ключа, схемы, обработка ошибок
  messaging/
    broker.py     брокер, обменники и очереди RabbitMQ
    consumer.py   обработчик сообщений с retry
    outbox_relay.py публикация событий из outbox
  main.py         приложение FastAPI
alembic/          миграции
tests/
  unit/           тесты без внешних зависимостей
  integration/    тесты на PostgreSQL в testcontainers
Dockerfile
docker-compose.yml
```

Зависимости направлены внутрь: `api` и `messaging` вызывают сервисы, сервисы работают с базой через Unit of Work и репозитории, `domain` ни от чего не зависит. Поэтому сервисы можно тестировать без HTTP и брокера.
