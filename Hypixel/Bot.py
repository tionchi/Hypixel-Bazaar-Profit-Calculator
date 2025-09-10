import tkinter as tk
from tkinter import ttk
import requests
import threading
import time
import math
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import date2num
import matplotlib.dates as mdates
import datetime
import numpy as np
from bs4 import BeautifulSoup

CATEGORY_MAP = {
    "Enchantment Books": ["ENCHANTED_BOOK", "BOOK"],
    "Food": ["APPLE", "CAKE", "BREAD", "CARROT", "POTION"],
    "Ores": ["COAL", "IRON", "GOLD", "DIAMOND", "EMERALD"],
    "Mob Drops": ["BLAZE_ROD", "GHAST_TEAR", "SPIDER_EYE"],
    "Other": []
}

class BazaarFlippingBot:
    def __init__(self, root):
        self.root = root
        self.root.title("Hypixel Bazaar Flipping Bot")
        self.root.geometry("950x900")

        filter_frame = ttk.Frame(root)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(filter_frame, text="Category:").pack(side=tk.LEFT, padx=5)
        self.category_var = tk.StringVar(value="All")
        categories = ["All"] + list(CATEGORY_MAP.keys())
        self.category_combo = ttk.Combobox(filter_frame, values=categories, textvariable=self.category_var, state="readonly", width=20)
        self.category_combo.pack(side=tk.LEFT)
        self.category_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        ttk.Label(filter_frame, text="Min Price:").pack(side=tk.LEFT, padx=5)
        self.min_price_var = tk.StringVar()
        self.min_price_entry = ttk.Entry(filter_frame, textvariable=self.min_price_var, width=10)
        self.min_price_entry.pack(side=tk.LEFT)
        self.min_price_var.trace_add("write", lambda *args: self.apply_filters())

        ttk.Label(filter_frame, text="Max Price:").pack(side=tk.LEFT, padx=5)
        self.max_price_var = tk.StringVar()
        self.max_price_entry = ttk.Entry(filter_frame, textvariable=self.max_price_var, width=10)
        self.max_price_entry.pack(side=tk.LEFT)
        self.max_price_var.trace_add("write", lambda *args: self.apply_filters())

        columns = ("Product ID", "Buy Price", "Sell Price", "Spread", "Margin", "Volume", "Score")
        self.tree = ttk.Treeview(root, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120 if col != "Product ID" else 180)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(root, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.figure_main, self.ax_main = plt.subplots(figsize=(8,4))
        self.canvas_main = FigureCanvasTkAgg(self.figure_main, master=root)
        self.canvas_main.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.figure_candle, self.ax_candle = plt.subplots(figsize=(8,4))
        self.canvas_candle = FigureCanvasTkAgg(self.figure_candle, master=root)
        self.canvas_candle.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.products_data = []
        self.all_products = {}
        self.scraped_history = {}

        self.running = True
        threading.Thread(target=self.update_data, daemon=True).start()
        self.start_scraper()

    def scrape_history(self, product_id):
        url = f"https://bazaartracker.com/product/{product_id}"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')

            history = []
            table = soup.find('table')
            if not table:
                return history

            for row in table.tbody.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 2:
                    continue
                try:
                    ts = datetime.datetime.strptime(cols[0].text.strip(), '%Y-%m-%d %H:%M')
                    price = float(cols[1].text.strip().replace(',', ''))
                    history.append((ts, price))
                except:
                    continue
            return history
        except Exception as e:
            print(f"Failed to scrape {product_id}: {e}")
            return []

    def start_scraper(self):
        def loop():
            while self.running:
                items = list({item['product_id'] for item in self.products_data})
                for item in items:
                    self.scraped_history[item] = self.scrape_history(item)
                    time.sleep(1)
                time.sleep(300)
        threading.Thread(target=loop, daemon=True).start()

    def update_data(self):
        while self.running:
            try:
                response = requests.get("https://api.hypixel.net/skyblock/bazaar")
                json_data = response.json()
                products = json_data.get("products", {})

                flip_opportunities = []

                for product_id, product_data in products.items():
                    quick = product_data.get("quick_status")
                    if not quick:
                        continue
                    sell_price = quick.get("sellPrice", 0)
                    buy_price = quick.get("buyPrice", 0)
                    buy_vol = quick.get("buyVolume", 0)
                    sell_vol = quick.get("sellVolume", 0)

                    spread = buy_price - sell_price
                    volume = buy_vol + sell_vol

                    if spread > 0 and volume > 100:
                        volume_ratio = min(buy_vol, sell_vol) / max(buy_vol, sell_vol) if max(buy_vol, sell_vol) > 0 else 0
                        rel_spread = spread / sell_price if sell_price else 0
                        # Example scoring prioritizing buy liquidity a bit more:
                        score = (rel_spread ** 0.5) * (buy_vol ** 1.2) * (sell_vol ** 0.8) * volume_ratio

                        if volume < 500:
                            score *= (volume / 500)

                        flip_opportunities.append({
                            "product_id": product_id,
                            "sell_price": round(sell_price, 2),
                            "buy_price": round(buy_price, 2),
                            "spread": round(spread, 2),
                            "margin": round(rel_spread * 100, 2),
                            "buy_volume": buy_vol,
                            "sell_volume": sell_vol,
                            "volume": volume,
                            "score": round(score, 2)
                        })

                self.products_data = flip_opportunities
                self.all_products = products
                self.apply_filters()
                time.sleep(10)
            except Exception as e:
                print("Error fetching data:", e)
                time.sleep(10)

    def apply_filters(self):
        filtered = self.products_data

        cat = self.category_var.get()
        if cat != "All":
            keywords = CATEGORY_MAP.get(cat, [])
            if keywords:
                filtered = [item for item in filtered if any(k in item["product_id"] for k in keywords)]

        try:
            min_price = float(self.min_price_var.get())
            filtered = [item for item in filtered if item["sell_price"] >= min_price]
        except ValueError:
            pass

        try:
            max_price = float(self.max_price_var.get())
            filtered = [item for item in filtered if item["sell_price"] <= max_price]
        except ValueError:
            pass

        filtered.sort(key=lambda x: x["score"], reverse=True)

        self.tree.delete(*self.tree.get_children())
        for item in filtered[:20]:
            self.tree.insert('', tk.END, values=(
                item["product_id"],
                item["buy_price"],
                item["sell_price"],
                item["spread"],
                item["margin"],
                item["volume"],
                item["score"],
            ))

        self.ax_main.clear()
        if filtered:
            names = [x["product_id"] for x in filtered[:10]]
            scores = [x["score"] for x in filtered[:10]]
            self.ax_main.barh(names[::-1], scores[::-1], color='skyblue')
            self.ax_main.set_xlabel("Flip Score (Profit × log(Volume))")
            self.ax_main.set_title("Top Flip Opportunities by Score (Filtered)")
            self.figure_main.tight_layout()
            self.canvas_main.draw()

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        product_id = item["values"][0]
        self.plot_scraped_history(product_id)

    def plot_scraped_history(self, product_id):
        data = self.scraped_history.get(product_id, [])
        if not data:
            print(f"No scraped history for {product_id}")
            return

        times, prices = zip(*data)
        self.ax_candle.clear()
        self.ax_candle.plot(times, prices, '-o', markersize=3)
        self.ax_candle.set_title(f"Scraped Bazaar History: {product_id}")
        self.ax_candle.set_ylabel("Price")
        self.ax_candle.xaxis.set_major_formatter(mdates.DateFormatter('%d %H:%M'))
        self.ax_candle.grid(True)
        self.figure_candle.tight_layout()
        self.canvas_candle.draw()

    def stop(self):
        self.running = False

if __name__ == "__main__":
    root = tk.Tk()
    app = BazaarFlippingBot(root)
    root.protocol("WM_DELETE_WINDOW", app.stop)
    root.mainloop()
