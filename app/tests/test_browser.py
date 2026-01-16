from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        # Запускаем браузер (headless=False, чтобы ты увидел окно, если у тебя есть интерфейс)
        # Если ты на сервере без монитора, поставь headless=True
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page()
        page.goto("https://jp.mercari.com")
        print("Заголовок страницы:", page.title())
        browser.close()

if __name__ == "__main__":
    run()