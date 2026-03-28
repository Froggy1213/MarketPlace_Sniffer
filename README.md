# 🛍️ MarketPlace Sniffer

[![CI Pipeline](https://github.com/Froggy1213/MarketPlace_Sniffer/actions/workflows/ci.yml/badge.svg)](https://github.com/Froggy1213/MarketPlace_Sniffer/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![uv](https://img.shields.io/badge/uv-Fast_Python-purple.svg)](https://github.com/astral-sh/uv)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Celery](https://img.shields.io/badge/Celery-Distributed_Tasks-37814A.svg?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Real-time marketplace intelligence for Japan's top platforms — delivered straight to Telegram.**

MarketPlace Sniffer is a production-grade, multi-tenant SaaS bot that continuously monitors **Mercari, Yahoo Auctions, Rakuma, Rakuten,** and **PayPay Flea Market** for new listings matching your criteria. The moment a match appears — you get notified. Before anyone else.

---

## ✨ Why MarketPlace Sniffer?

Japan's resale market moves fast. Rare items sell in minutes. MarketPlace Sniffer gives you an unfair advantage:

- 🎯 **Keyword + price range targeting** across 5 platforms simultaneously
- ⚡ **Sub-minute detection latency** via distributed Celery workers
- 🧠 **Zero duplicate noise** — PostgreSQL deduplication ensures every notification is unique
- 📸 **Rich notifications** — photo, title, price, and a direct buy link in one message
- 🤖 **Fully automated** — set it and forget it

---

## 🚀 Key Features

### 🏪 Universal Marketplace Coverage
Plugin architecture (Open/Closed Principle) makes adding new platforms trivial. Currently supported:

| Platform | Type | Status |
| :--- | :--- | :--- |
| Mercari Japan | C2C | ✅ Live |
| Yahoo Auctions | C2C Auction | ✅ Live |
| Rakuma | C2C | ✅ Live |
| Rakuten | B2C | ✅ Live |
| PayPay Flea Market | C2C | ✅ Live |

### 👥 Multi-Tenant Architecture
Every user manages their own independent search tasks. The scraping engine intelligently **batches identical queries** from different users into a single browser session — slashing CPU and RAM overhead at scale.

### 🛡️ Anti-Ban Engine
Sustained scraping without getting blocked requires more than just proxies:
- Dynamic request throttling with human-like timing variance
- User-agent rotation per session
- Headless Chromium with media disabled (bandwidth optimization)
- Shared Playwright context per worker cycle (eliminates memory leaks)

### 💬 Premium Telegram UX
No commands to memorize. A guided **FSM (Finite State Machine)** flow walks users through setup:
- Persistent Reply Menu for instant navigation
- Contextual Inline Keyboards with price presets
- Per-task delete buttons directly in the task list
- HTML-formatted rich notifications with product images

---

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────┐
│                   Docker Network                    │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌───────────────┐  │
│  │   bot    │    │ worker   │    │     beat      │  │
│  │ Aiogram  │    │Playwright│    │ Celery CRON   │  │
│  │ FSM/UX   │    │ Scraper  │    │  Scheduler    │  │
│  └────┬─────┘    └────┬─────┘    └───────┬───────┘  │
│       │               │                  │          │
│  ┌────▼───────────────▼──────────────────▼───────┐  │
│  │                   Redis                       │  │
│  │            Message Broker / Queue             │  │
│  └────────────────────┬──────────────────────────┘  │
│                       │                             │
│               ┌───────▼────────┐                    │
│               │   PostgreSQL   │                    │
│               │  Async + ORM   │                    │
│               └────────────────┘                    │
└─────────────────────────────────────────────────────┘
```

**5 isolated containers, zero single points of failure:**

| Container | Role |
| :--- | :--- |
| `bot` | Aiogram 3.x — FSM, keyboards, user interactions |
| `worker` | Async Playwright — scraping execution |
| `beat` | Celery Beat — CRON-based task scheduling |
| `redis` | Message broker + task queue |
| `db` | PostgreSQL 15 — persistent storage |

---

## 🛠 Tech Stack

| Layer | Technology |
| :--- | :--- |
| Language | Python 3.13 + `uv` package manager |
| Browser Automation | Async Playwright (Chromium) |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (Async), Alembic |
| Bot Framework | Aiogram 3.x (FSM, Inline + Reply Keyboards) |
| CI/CD | GitHub Actions — Mypy + Ruff |
| Containerization | Docker + Docker Compose |

---

## ⚙️ Setup & Installation

**1. Clone the repository**
```bash
git clone https://github.com/Froggy1213/MarketPlace_Sniffer.git
cd MarketPlace_Sniffer
```

**2. Configure environment**
```bash
cp .env.example .env
```
Fill in your credentials:
```env
TELEGRAM_BOT_TOKEN=your_token_here
ADMIN_ID=your_telegram_id
POSTGRES_URL=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0
```

**3. Launch the full cluster**
```bash
docker compose up -d --build
```

**4. Apply database migrations**
```bash
docker exec -it mercari_bot uv run alembic upgrade head
```

That's it. The bot is live.

---

## 🎮 Usage

Send `/start` — the bot handles the rest.

| Action | How |
| :--- | :--- |
| Create a search task | `➕ New search` → pick platform → enter keyword → set price range |
| View active tasks | `📋 My tasks` → see all tasks with inline delete buttons |
| Delete a task | Press `❌ Delete` on any task card |
| Get help | `ℹ️ Help` |

---

## ⚠️ Disclaimer

This project is intended for educational and portfolio purposes. The author is not responsible for any misuse. Please respect the Terms of Service and rate limits of the target platforms.