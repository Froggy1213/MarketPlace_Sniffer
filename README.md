# 🕵️‍♂️ MarketPlace Sniffer

An advanced Telegram bot for monitoring Japanese marketplaces (**Mercari JP** & **Yahoo Auctions**).
The bot automatically finds new items based on search criteria, filters duplicates using a database, and sends instant notifications with photos and prices.

## 🚀 Key Features

* **Multi-Platform:** Supports both Mercari Japan and Yahoo Auctions.
* **Anti-Ban System:** Simulates human behavior with random delays, user-agent rotation, and request shuffling.
* **Smart Filtering:** Uses PostgreSQL to store history and prevent duplicate notifications.
* **Interactive Control:** Manage search URLs directly via Telegram commands.
* **Dockerized:** Easy deployment with Docker Compose.

## 🛠 Tech Stack

* **Language:** Python 3.10
* **Browser Automation:** Playwright (Chromium)
* **Telegram Bot:** Aiogram 3.x
* **Database:** PostgreSQL + SQLAlchemy
* **Scheduling:** APScheduler
* **Infrastructure:** Docker & Docker Compose

## ⚙️ Setup & Installation

1.  **Clone the repository**
    ```bash
    git clone [https://github.com/Froggy1213/MarketPlace_Sniffer.git](https://github.com/Froggy1213/MarketPlace_Sniffer.git)
    cd MarketPlace_Sniffer
    ```

2.  **Configure Environment**
    Create a `.env` file based on the example:
    ```bash
    cp .env.example .env
    ```
    *Open `.env` and fill in your `TELEGRAM_BOT_TOKEN` and `ADMIN_ID`.*

3.  **Run with Docker**
    ```bash
    docker compose up -d --build
    ```

## 🎮 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Check connection and see help. |
| `/add <url>` | Add a new search URL (Mercari or Yahoo). |
| `/list` | Show all active tracking URLs. |
| `/del <id>` | Delete a search by ID (get ID from `/list`). |

## ⚠️ Disclaimer

This project is for educational purposes only. The author is not responsible for any misuse of this software. Please respect the Terms of Service of the target platforms.