<p align="center">
  <img src="logo.svg" width="120" alt="Vnish HA logo">
</p>

<h1 align="center">vnish-ha</h1>

<p align="center">
  Интеграция Home Assistant для ASIC-майнеров на прошивке <a href="https://anthill.farm">Vnish (AnthillOS)</a>
</p>

<p align="center">
  <a href="https://github.com/temandroid/vnish-ha/releases"><img src="https://img.shields.io/github/v/release/temandroid/vnish-ha?style=flat-square" alt="Release"></a>
  <img src="https://img.shields.io/badge/HA-2024.1%2B-blue?style=flat-square" alt="HA 2024.1+">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT">
</p>

---

## Возможности

| Тип | Сущности |
|---|---|
| **Сенсоры** | Хэшрейт (реальный / средний / номинальный), потребляемая мощность (Вт), эффективность (Дж/ТХ), температуры платы и чипов (мин/макс), обороты вентиляторов (%), аппаратные ошибки (%), состояние майнера, счётчик перезапусков, активный пул, принятые/отклонённые шары, пинг пула |
| **Бинарный сенсор** | Майнинг (работает / остановлен) |
| **Переключатель** | Майнинг вкл/выкл |
| **Кнопки** | Перезагрузка, перезапуск майнинга, пауза, возобновление |

## Требования

- ASIC-майнер с прошивкой Vnish (AnthillOS)
- Home Assistant 2024.1+

## Установка

### HACS (рекомендуется)

1. HACS → Настройки → Пользовательские репозитории
2. Добавить `temandroid/vnish-ha`, категория `Integration`
3. Установить и перезапустить HA

### Вручную

Скопировать `custom_components/vnish/` в `<HA config>/custom_components/`.

## Настройка

1. Настройки → Устройства и службы → Добавить интеграцию → **Vnish Miner**
2. Ввести IP-адрес майнера (например `192.168.1.100`)
3. Опционально — API-ключ (создаётся в веб-интерфейсе прошивки → API Keys)

Интервал опроса (по умолчанию 30 сек) меняется через **Настроить** на карточке интеграции.

## Протестировано на

- Antminer S19k Pro, Vnish 1.3.3

## API

Интеграция использует локальный REST API `/api/v1` прошивки Vnish.  
Аутентификация через заголовок `x-api-key` (опционально — большинство запросов доступны анонимно).
