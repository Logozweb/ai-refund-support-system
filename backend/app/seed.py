from datetime import date, timedelta

# id, name, email, tier, refunds_90d, damage_claims_12m
CUSTOMERS = [
    (1, "Amara Okafor", "amara.okafor@example.com", "Gold", 0, 0),
    (2, "Liam Carter", "liam.carter@example.com", "Standard", 1, 0),
    (3, "Sofia Rossi", "sofia.rossi@example.com", "Standard", 0, 0),
    (4, "Daniel Kim", "daniel.kim@example.com", "Gold", 0, 0),
    (5, "Priya Nair", "priya.nair@example.com", "Standard", 0, 1),
    (6, "Marcus Johnson", "marcus.johnson@example.com", "Standard", 4, 0),
    (7, "Elena Petrov", "elena.petrov@example.com", "Standard", 0, 0),
    (8, "Tunde Bello", "tunde.bello@example.com", "Silver", 0, 0),
    (9, "Hannah Muller", "hannah.muller@example.com", "Silver", 1, 0),
    (10, "Carlos Diaz", "carlos.diaz@example.com", "Standard", 1, 0),
    (11, "Aisha Rahman", "aisha.rahman@example.com", "Gold", 0, 0),
    (12, "Oliver Grant", "oliver.grant@example.com", "Standard", 0, 0),
    (13, "Mei Lin", "mei.lin@example.com", "Silver", 0, 0),
    (14, "Jack Turner", "jack.turner@example.com", "Standard", 2, 3),
    (15, "Zainab Yusuf", "zainab.yusuf@example.com", "Gold", 0, 0),
]
# id, customer, ordered_days_ago, delivered_days_ago|None, status, refunded, items[(sku,name,price,qty,final_sale)]
ORDERS = [
    ("ORD-1001", 1, 12, 5, "delivered", 0, [("HP-01", "Wireless Headphones", 89.99, 1, 0)]),
    ("ORD-1017", 1, 66, 60, "delivered", 0, [("PC-07", "Phone Case", 19.00, 1, 0)]),
    ("ORD-1002", 2, 46, 40, "delivered", 0, [("RS-22", "Running Shoes", 120.00, 1, 0)]),
    ("ORD-1019", 2, 3, None, "cancelled", 0, [("BP-03", "Backpack", 65.00, 1, 0)]),
    ("ORD-1003", 3, 15, 10, "delivered", 0, [("CJ-09", "Clearance Jacket", 60.00, 1, 1)]),
    ("ORD-1018", 3, 11, 7, "delivered", 0, [("WC-11", "Winter Coat", 520.00, 1, 0)]),
    ("ORD-1004", 4, 13, 8, "delivered", 0, [("MN-4K", "4K Monitor", 649.00, 1, 0)]),
    ("ORD-1005", 5, 8, 3, "delivered", 0, [("BL-02", "Blender", 79.50, 1, 0), ("MG-05", "Ceramic Mug Set", 34.00, 1, 0)]),
    ("ORD-1006", 6, 17, 12, "delivered", 0, [("SP-08", "Bluetooth Speaker", 59.00, 1, 0)]),
    ("ORD-1007", 7, 4, None, "shipped", 0, [("SW-12", "Smartwatch", 199.00, 1, 0)]),
    ("ORD-1008", 8, 26, 20, "delivered", 0, [("LS-04", "Laptop Stand", 45.00, 1, 0)]),
    ("ORD-1009", 9, 40, 35, "delivered", 0, [("EM-30", "Espresso Machine", 230.00, 1, 0)]),
    ("ORD-1010", 10, 11, 6, "delivered", 1, [("DL-06", "Desk Lamp", 39.00, 1, 0)]),
    ("ORD-1011", 11, 20, 15, "delivered", 0, [("GL-99", "Gaming Laptop", 1299.00, 1, 0)]),
    ("ORD-1012", 12, 4, 2, "delivered", 0, [("GC-50", "Digital Gift Card", 50.00, 1, 1)]),
    ("ORD-1013", 13, 33, 28, "delivered", 0, [("YM-01", "Yoga Mat", 35.00, 1, 0), ("WB-02", "Water Bottle", 22.00, 1, 0)]),
    ("ORD-1014", 14, 14, 9, "delivered", 0, [("CL-50", "Camera Lens", 340.00, 1, 0)]),
    ("ORD-1015", 15, 19, 14, "delivered", 0, [("KB-10", "Mechanical Keyboard", 110.00, 1, 0)]),
    ("ORD-1016", 15, 8, 4, "delivered", 0, [("EB-15", "Noise-Cancelling Earbuds", 149.00, 1, 0)]),
]

def seed(db):
    if db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]:
        return
    today = date.today()
    d = lambda n: None if n is None else (today - timedelta(days=n)).isoformat()
    db.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", CUSTOMERS)
    for oid, cid, od, dd, st, rf, items in ORDERS:
        total = sum(p * q for _, _, p, q, _ in items)
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", (oid, cid, d(od), d(dd), st, round(total, 2), rf))
        db.executemany("INSERT INTO order_items(order_id,sku,name,price,qty,final_sale) VALUES (?,?,?,?,?,?)",
                       [(oid, *i) for i in items])
    db.commit()
