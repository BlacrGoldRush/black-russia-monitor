import os
import requests
from bs4 import BeautifulSoup
from flask import Flask
import threading
import time
import logging
import re

app = Flask(__name__)

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8353596700:AAGGBzOlnQZepaq0lnXys4KlQNKozJpXq7A")
CHAT_ID = os.environ.get("CHAT_ID", "5316017487")

# ТОЛЬКО BLACK RUSSIA - ИГРОВАЯ ВАЛЮТА
FUNPAY_URLS = {
    "Black Russia - Валюта": "https://funpay.com/chips/186/"
}

CHECK_INTERVAL = 300  # 5 минут
MAX_PRICE = 10000

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

monitor_running = False
monitor_thread = None
seen_items = []

# ================= ФУНКЦИИ =================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Сообщение отправлено")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        return False

def smart_parse_black_russia(url, category):
    """Умный парсинг именно для Black Russia"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        logger.info(f"🔍 Парсинг {category}...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ Ошибка HTTP: {response.status_code}")
            return []
        
        # Проверяем, что получили нормальную страницу
        if len(response.text) < 1000:
            logger.error("❌ Страница слишком короткая, возможно блокировка")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Способ 1: Прямой поиск по структуре FunPay
        items = []
        
        # Ищем все элементы, которые могут быть товарами
        # На FunPay товары обычно в таких структурах:
        
        # Вариант A: Элементы с классом, содержащим "item"
        potential_items = soup.find_all(class_=lambda x: x and any(word in str(x).lower() for word in ['item', 'lot', 'offer', 'product']))
        
        # Вариант B: Все div с классами
        if not potential_items:
            potential_items = soup.find_all('div', class_=True)
        
        logger.info(f"🔎 Найдено потенциальных элементов: {len(potential_items)}")
        
        for elem in potential_items[:50]:  # Проверяем первые 50
            try:
                text = elem.get_text(strip=True, separator=' ')
                
                # Фильтруем - должен быть текст про Black Russia и цена
                if not text or len(text) > 500:
                    continue
                
                # Должно содержать ключевые слова
                keywords = ['black', 'russia', 'black russia', 'br', 'валюта', 'золот', 'gold', 'руб', '₽']
                has_keyword = any(keyword in text.lower() for keyword in keywords)
                
                if not has_keyword:
                    continue
                
                # Ищем цену (цифры от 3 до 6 знаков)
                price_match = re.search(r'\b(\d{3,6})\b', text)
                if not price_match:
                    continue
                
                price = int(price_match.group(1))
                
                # Фильтруем по цене
                if price < 10 or price > MAX_PRICE:
                    continue
                
                # Ищем ссылку
                link = url
                link_elem = elem.find('a', href=True)
                if link_elem:
                    href = link_elem['href']
                    if href.startswith('/'):
                        link = f"https://funpay.com{href}"
                    elif href.startswith('http'):
                        link = href
                
                # Формируем заголовок
                lines = text.split('.')
                title = lines[0].strip() if lines else text[:60]
                
                items.append({
                    'id': f"{hash(text)}_{price}",
                    'title': title[:80],
                    'price': price,
                    'link': link,
                    'category': category
                })
                
                logger.info(f"   ✅ Найден товар: {title[:40]}... - {price} руб.")
                
            except Exception as e:
                continue
        
        logger.info(f"🎯 Всего найдено товаров: {len(items)}")
        return items
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")
        return []

def monitor_loop():
    global monitor_running, seen_items
    
    logger.info("🚀 Запуск мониторинга Black Russia...")
    send_telegram("🎮 <b>Black Russia Monitor запущен!</b>\nМониторю валюту на FunPay...")
    
    check_count = 0
    
    while monitor_running:
        try:
            check_count += 1
            current_time = time.strftime("%H:%M:%S")
            
            logger.info(f"🔍 Проверка #{check_count} в {current_time}")
            
            # Парсим только валюту Black Russia
            all_new_items = []
            
            for category, url in FUNPAY_URLS.items():
                items = smart_parse_black_russia(url, category)
                new_items = [item for item in items if item['id'] not in seen_items]
                
                if new_items:
                    logger.info(f"🎯 Новых товаров: {len(new_items)}")
                    all_new_items.extend(new_items)
                    
                    # Добавляем в историю
                    for item in new_items:
                        seen_items.append(item['id'])
            
            # Отправляем уведомления
            if all_new_items:
                logger.info(f"📨 Отправляю {len(all_new_items)} уведомлений...")
                send_telegram(f"🎮 <b>Black Russia - найдено {len(all_new_items)} новых предложений!</b>")
                
                for i, item in enumerate(all_new_items[:5], 1):
                    message = f"""
🏆 <b>BLACK RUSSIA #{i}</b>

💰 {item['price']} руб.
📝 {item['title']}

🔗 <a href="{item['link']}">КУПИТЬ НА FUNPAY</a>
                    """
                    send_telegram(message)
                    time.sleep(1)
            else:
                logger.info("📭 Новых товаров не найдено")
                
                # Раз в 10 проверок отправляем статус
                if check_count % 10 == 0:
                    send_telegram(f"♻️ Проверка #{check_count} - новых предложений нет")
            
            # Ждем перед следующей проверкой
            logger.info(f"⏰ Следующая проверка через {CHECK_INTERVAL//60} минут...")
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге: {e}")
            time.sleep(60)
    
    logger.info("🛑 Мониторинг остановлен")
    send_telegram("🛑 <b>Black Russia Monitor остановлен</b>")

# ================= ВЕБ-ИНТЕРФЕЙС =================

@app.route('/')
def home():
    return """
    <h1>🎮 Black Russia Monitor</h1>
    <p>Мониторинг валюты Black Russia на FunPay</p>
    <p><a href="/start">▶️ Запустить мониторинг</a></p>
    <p><a href="/stop">⏹️ Остановить мониторинг</a></p>
    <p><a href="/test">🧪 Тест парсинга</a></p>
    <p><a href="/stats">📊 Статистика</a></p>
    <p><a href="/health">❤️ Проверка работы</a></p>
    """

@app.route('/start')
def start_monitor():
    global monitor_running, monitor_thread
    if not monitor_running:
        monitor_running = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        return "✅ Мониторинг Black Russia запущен!"
    return "⚠️ Мониторинг уже запущен"

@app.route('/stop')
def stop_monitor():
    global monitor_running
    monitor_running = False
    return "⏹️ Мониторинг остановлен"

@app.route('/test')
def test_parse():
    """Тестовый парсинг прямо сейчас"""
    results = []
    for category, url in FUNPAY_URLS.items():
        items = smart_parse_black_russia(url, category)
        results.append({
            'category': category,
            'found': len(items),
            'items': items[:10]  # Первые 10
        })
    
    html = "<h1>🧪 Тестовый парсинг Black Russia</h1>"
    for result in results:
        html += f"<h2>{result['category']}: {result['found']} товаров</h2>"
        if result['items']:
            for item in result['items']:
                html += f"""
                <div style="border:1px solid #ccc;padding:10px;margin:5px;">
                    <p><b>{item['title']}</b></p>
                    <p>💰 Цена: {item['price']} руб.</p>
                    <p>🔗 <a href='{item['link']}' target='_blank'>Ссылка на товар</a></p>
                </div>
                """
        else:
            html += "<p>❌ Товары не найдены</p>"
        html += "<hr>"
    
    return html

@app.route('/stats')
def stats():
    from datetime import datetime
    return f"""
    <h1>📊 Статистика</h1>
    <p>Время: {datetime.now().strftime('%H:%M:%S')}</p>
    <p>В памяти товаров: {len(seen_items)}</p>
    <p>Мониторинг: {'✅ Запущен' if monitor_running else '❌ Остановлен'}</p>
    <p>Токен бота: {'✅ Настроен' if BOT_TOKEN else '❌ Не настроен'}</p>
    <p>Chat ID: {CHAT_ID}</p>
    """

@app.route('/health')
def health():
    return "✅ Black Russia Monitor работает", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
