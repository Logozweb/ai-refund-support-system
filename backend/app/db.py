import os, sqlite3
from .seed import seed

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, tier TEXT,
  refunds_90d INTEGER, damage_claims_12m INTEGER);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
  order_date TEXT, delivered_date TEXT, status TEXT, total REAL, refunded INTEGER);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT REFERENCES orders(id),
  sku TEXT, name TEXT, price REAL, qty INTEGER, final_sale INTEGER);
CREATE TABLE IF NOT EXISTS refund_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
  customer_email TEXT, order_id TEXT, message TEXT, reason TEXT, decision TEXT, decision_code TEXT,
  amount REAL, reply TEXT, flags TEXT, trace TEXT, ai TEXT, audit TEXT,
  status TEXT DEFAULT 'closed', final_decision TEXT, resolved_note TEXT);
"""

def path():
    return os.getenv("DB_PATH", "/data/support.db")

def conn():
    c = sqlite3.connect(path())
    c.row_factory = sqlite3.Row
    return c

def init():
    os.makedirs(os.path.dirname(path()) or ".", exist_ok=True)
    c = conn()
    c.executescript(SCHEMA)
    seed(c)
    c.close()
