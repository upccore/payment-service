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

Поднимаются пять сервисов:

| Сервис | Что делает |
|---|---|
| `postgres`, `rabbitmq` | база данных и брокер |
| `api` | HTTP API; при старте применяет миграции |
| `outbox-relay` | публикует события из таблицы `outbox` в RabbitMQ |
| `consumer` | обрабатывает платежи и отправляет webhook |

`outbox-relay` и `consumer` стартуют, когда `api` проходит healthcheck, то есть миграции уже применены.

| Что | Адрес |
|---|---|
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 (`guest` / `guest`) |

API-ключ по умолчанию — `secret-api-key`. Свой ключ задаётся переменной окружения `API_KEY`:

```bash
API_KEY=my-key docker compose up --build
```

или через файл `.env`, который docker compose читает автоматически:

```bash
cp .env.example .env
```

Остальные настройки задаются переменными окружения сервисов `api` и `consumer`:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | — | строка подключения к PostgreSQL |
| `RABBITMQ_URL` | — | строка подключения к RabbitMQ |
| `API_KEY` | — | ключ для заголовка `X-API-Key` |
| `DB_POOL_SIZE` | `10` | размер пула соединений с базой |
| `DB_MAX_OVERFLOW` | `5` | сколько соединений можно открыть сверх пула |
| `CONSUMER_PREFETCH` | `10` | сколько сообщений consumer обрабатывает одновременно; не больше `DB_POOL_SIZE` |
| `GATEWAY_TIMEOUT` | `30` | таймаут вызова платёжного шлюза, секунды |
| `LOG_LEVEL` | `INFO` | уровень логирования |

Остановка с удалением данных:

```bash
docker compose down -v
```

## API

Все запросы к `/api/v1/payments` требуют заголовок `X-API-Key`. Без него или с неверным ключом сервис отвечает `401`.

### Health check

`GET /health` — без API-ключа. Проверяет соединение с базой: `200 {"status": "ok"}` или `503`, если база недоступна. Его использует healthcheck в docker compose.

### Создание платежа

`POST /api/v1/payments`

Заголовок `Idempotency-Key` обязателен. Повтор с тем же ключом и теми же параметрами возвращает уже созданный платёж, с другими параметрами — `409 Conflict`.

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
                  outbox-relay
                        │
              exchange "payments" ──> queue "payments.new" ──> consumer ──> webhook
                    ▲                                             │
                    │                                  ошибка, попытка 1 или 2
                    │                                             │
                    │                                 exchange "payments.retry"
                    │                                             │
                    └── по истечении TTL ── queue "payments.retry.1000ms" (TTL 1 с)
                                            queue "payments.retry.2000ms" (TTL 2 с)

consumer ── ошибка, попытка 3 ──> exchange "payments.dlx" ──> queue "payments.dlq"
```

1. `api` в одной транзакции сохраняет платёж со статусом `pending` и событие в таблицу `outbox`.
2. `outbox-relay` раз в секунду читает неотправленные события, публикует их в очередь `payments.new` и отмечает время публикации.
3. `consumer` получает сообщение, эмулирует обработку в шлюзе (2–5 секунд, 90% успех, 10% ошибка), сохраняет статус `succeeded` или `failed` и отправляет webhook.

### Outbox

Платёж и событие записываются атомарно, поэтому событие не теряется, даже если RabbitMQ недоступен в момент создания платежа: оно останется в `outbox` и будет опубликовано, когда брокер вернётся.

Событие может быть опубликовано повторно, если сервис упадёт между публикацией и фиксацией отметки. Это безопасно: consumer проводит платёж только в статусе `pending`.

### Идемпотентность

На `idempotency_key` стоит уникальный индекс. Повторный запрос с тем же ключом не создаёт новый платёж:

- если сумма, валюта, описание, метаданные и `webhook_url` совпадают с сохранёнными, возвращается существующий платёж с кодом `202`;
- если хотя бы одно поле отличается, сервис отвечает `409 Conflict` и ничего не меняет.

Параметры сравниваются как значения: `"100.5"` и `"100.50"` — одна и та же сумма, порядок ключей в `metadata` не важен.

Если два запроса с одним ключом приходят одновременно, вставка второго упирается в уникальный индекс. Сервис откатывает только её (savepoint), читает платёж, созданный первым запросом, и применяет к нему те же правила.

### Обработка платежа и защита от двойного списания

Consumer читает платёж с `SELECT ... FOR UPDATE` и держит блокировку строки, пока вызывает шлюз и сохраняет результат. Если одно событие пришло дважды (повтор из outbox или retry), второй обработчик ждёт, пока первый завершит транзакцию, видит, что платёж уже не `pending`, и шлюз не вызывает.

Почему блокировка, а не условный `UPDATE ... WHERE status = 'pending'` после вызова шлюза: условный UPDATE не даст сохранить второй результат, но не помешает второму вызову шлюза, а с реальным шлюзом это двойное списание. Промежуточный статус `processing` или аренда с отдельной колонкой решили бы это без долгой транзакции, но добавили бы статус сверх заданных и логику восстановления зависших платежей. Здесь это не нужно:

- блокируется одна строка, а не таблица, и только на время вызова шлюза (2–5 секунд);
- вызов шлюза ограничен `GATEWAY_TIMEOUT`: по таймауту транзакция откатывается, блокировка снимается, событие уходит в retry;
- пул соединений с базой не меньше `CONSUMER_PREFETCH`, поэтому каждому обрабатываемому сообщению хватает соединения.

Webhook отправляется уже после фиксации транзакции и блокировку не держит.

### Retry и Dead Letter Queue

Обработка сообщения выполняется до 3 раз с экспоненциальной задержкой между попытками: 1 и 2 секунды. Ошибкой считается любой сбой обработки, включая недоставленный webhook.

Задержку выдерживает RabbitMQ, а не consumer:

1. Номер попытки хранится в заголовке `x-attempt`; у первой доставки его нет, это попытка 1.
2. Если попытка 1 или 2 не удалась, consumer публикует событие в обменник `payments.retry` с `x-attempt`, увеличенным на 1, и подтверждает исходное сообщение.
3. Событие попадает в очередь своей задержки: `payments.retry.1000ms` или `payments.retry.2000ms`. У этих очередей нет потребителей, а у сообщений в них ограничен срок жизни (`x-message-ttl`). Когда он истекает, RabbitMQ через dead-letter возвращает сообщение в `payments.new`.
4. После третьей неудачи сообщение отклоняется и через обменник `payments.dlx` попадает в очередь `payments.dlq`.

Так consumer не держит сообщение и слот prefetch, пока ждёт повтора, а ожидающие повторы переживают его перезапуск. Для каждой задержки своя очередь: в одной очереди с разным TTL у сообщений короткая задержка могла бы ждать, пока истечёт длинная, потому что RabbitMQ удаляет просроченные сообщения только из головы очереди.

Если consumer упадёт между публикацией в retry и подтверждением исходного сообщения, событие будет обработано дважды. Это безопасно по той же причине, что и для outbox.

При повторной попытке шлюз заново не вызывается, если статус платежа уже сохранён, — повторяется только отправка webhook.

Статус `failed` — это результат платежа, а не ошибка обработки: он сохраняется, webhook отправляется, повторов нет.

Посмотреть очереди:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

### Логи

Все сервисы пишут логи в одном формате. Пока consumer обрабатывает платёж, в каждой строке есть его идентификатор, включая строки SQLAlchemy и httpx:

```
2026-10-08 08:56:55,927 INFO app.services.processing [payment=d34bed51-...] Payment processed with status failed
2026-10-08 08:56:55,937 INFO app.services.webhooks [payment=d34bed51-...] Webhook delivered to http://hook/ok
```

Посмотреть путь одного платежа через все сервисы:

```bash
docker compose logs | grep d34bed51
```

Запросы healthcheck в access-лог не попадают.

## Принятые решения

- Публикация из outbox вынесена в отдельный сервис `outbox-relay`: `api` работает только с базой и не зависит от доступности RabbitMQ. Relay можно масштабировать: события выбираются с `FOR UPDATE SKIP LOCKED`, и два экземпляра не возьмут одно событие.
- Повторный запрос с тем же `Idempotency-Key` и теми же параметрами возвращает существующий платёж с кодом `202`, как и первый запрос: клиенту не нужно различать эти случаи.
- 3 попытки относятся к обработке сообщения целиком, а не только к отправке webhook.
- Задержка между попытками реализована retry-очередями RabbitMQ с TTL, а не плагином `rabbitmq_delayed_message_exchange`: решение работает на стандартном образе RabbitMQ.
- Consumer обрабатывает не более 10 сообщений одновременно (`CONSUMER_PREFETCH`).
- От двойного списания защищает блокировка строки платежа на время вызова шлюза, а не промежуточный статус: статусы остаются такими, как в задании.

## Тесты

Нужны Python 3.12 и запущенный Docker: интеграционные тесты поднимают PostgreSQL и RabbitMQ через testcontainers и применяют к базе миграции.

```bash
pip install -r requirements-dev.txt
pytest
```

Только unit-тесты, без Docker:

```bash
pytest -m "not integration"
```

Линтеры и проверка типов:

```bash
ruff check .
ruff format --check .
mypy app tests alembic/env.py
```

Те же команды есть в `Makefile`: `make test`, `make test-unit`, `make lint`, `make format`. В GitHub Actions на каждый push в `main` и на pull request запускаются линтеры, mypy и все тесты.

- `tests/unit` — сервисы на фейковых репозиториях, отправка webhook через `httpx.MockTransport`, решение «retry или DLQ» в `PaymentEventHandler`, чтение номера попытки подписчиком через `TestRabbitBroker`;
- `tests/integration` — API, outbox relay и обработка платежа на реальной базе, включая параллельные запросы с одним `Idempotency-Key` и параллельную обработку одного платежа; retry-очереди и DLQ на реальном RabbitMQ.

## Структура проекта

```
app/
  core/           настройки из переменных окружения, логирование
  domain/         статусы, валюты, данные нового платежа, доменные исключения
  db/             модели, сессия, Unit of Work
  repositories/   доступ к таблицам payments и outbox
  services/
    payments.py   создание и получение платежа, идемпотентность
    processing.py обработка платежа в consumer
    gateway.py    эмуляция платёжного шлюза
    protocols.py  интерфейсы шлюза и отправки webhook
    webhooks.py   отправка webhook
  api/            эндпоинты платежей и /health, проверка API-ключа, схемы, обработка ошибок
  messaging/
    queues.py     имена обменников и очередей, параметры retry
    broker.py     брокер и объявление топологии RabbitMQ
    consumer.py   подписчик на payments.new
    retry.py      обработка события: retry или DLQ
    outbox_relay.py публикация событий из outbox
    outbox_worker.py точка входа сервиса outbox-relay
    protocols.py  интерфейсы публикатора и обработчика
  main.py         приложение FastAPI
alembic/          миграции
tests/
  unit/           тесты без внешних зависимостей
  integration/    тесты на PostgreSQL и RabbitMQ в testcontainers
Dockerfile
docker-compose.yml
```

Зависимости направлены внутрь: `api` и `messaging` вызывают сервисы, сервисы работают с базой через Unit of Work и репозитории, `domain` ни от чего не зависит. Поэтому сервисы можно тестировать без HTTP и брокера.
