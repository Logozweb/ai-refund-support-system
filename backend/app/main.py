import json
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import db, llm
from .agent import process, now

@asynccontextmanager
async def lifespan(_):
    db.init()
    yield

app = FastAPI(title="AI Refund Support API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
POLICY = (Path(__file__).parent / "data" / "refund_policy.md").read_text()

class RefundIn(BaseModel):
    customer_email: str = Field(max_length=200)
    order_id: Optional[str] = Field(default=None, max_length=30)
    item_skus: List[str] = Field(default_factory=list, max_length=20)
    message: str = Field(min_length=1, max_length=4000)

class ResolveIn(BaseModel):
    decision: str = Field(pattern="^(Approved|Denied)$")
    note: str = Field(default="", max_length=500)

def row(r):
    d = dict(r)
    for k in ("flags", "trace", "ai", "audit"):
        if d.get(k): d[k] = json.loads(d[k])
    return d

@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": llm.provider()}

@app.get("/api/llm-check")
def llm_check(force: bool = False):
    """Live probe of the configured LLM. Open http://localhost:8000/api/llm-check to debug provider/key/model problems."""
    return llm.check(force)

@app.get("/api/policy")
def policy():
    return {"policy": POLICY}

@app.get("/api/customers")
def customers():
    c = db.conn()
    try:
        return [dict(r) for r in c.execute("SELECT id,name,email,tier FROM customers ORDER BY id")]
    finally: c.close()

@app.get("/api/orders")
def orders(email: str):
    c = db.conn()
    try:
        out = []
        for o in c.execute("SELECT o.* FROM orders o JOIN customers u ON u.id=o.customer_id WHERE lower(u.email)=? ORDER BY o.order_date DESC", (email.lower(),)):
            d = dict(o)
            d["items"] = [dict(i) for i in c.execute("SELECT sku,name,price,qty,final_sale FROM order_items WHERE order_id=?", (o["id"],))]
            out.append(d)
        return out
    finally: c.close()

@app.post("/api/refunds")
def create_refund(body: RefundIn):
    c = db.conn()
    try: return process(c, body)
    finally: c.close()

@app.get("/api/refunds")
def list_refunds(limit: int = 100):
    c = db.conn()
    try:
        rows = [row(r) for r in c.execute("SELECT * FROM refund_requests ORDER BY id DESC LIMIT ?", (min(limit, 500),))]
        stats = {"total": len(rows)}
        for k in ("Approved", "Denied", "Escalated"):
            stats[k.lower()] = sum(1 for r in rows if r["decision"] == k)
        stats["open_escalations"] = sum(1 for r in rows if r["status"] == "open")
        stats["injection_flags"] = sum(1 for r in rows if "prompt_injection_suspected" in (r["flags"] or []))
        return {"stats": stats, "requests": rows}
    finally: c.close()

@app.post("/api/refunds/{rid}/resolve")
def resolve(rid: int, body: ResolveIn):
    c = db.conn()
    try:
        r = c.execute("SELECT * FROM refund_requests WHERE id=?", (rid,)).fetchone()
        if not r: raise HTTPException(404, "Request not found")
        if r["status"] != "open": raise HTTPException(409, "Request is not awaiting human review")
        audit = json.loads(r["audit"]) + [{"ts": now(), "step": "human_resolution", "detail": f"Support agent set {body.decision}. {body.note}".strip()}]
        c.execute("UPDATE refund_requests SET status='closed', final_decision=?, resolved_note=?, audit=? WHERE id=?",
                  (body.decision, body.note, json.dumps(audit), rid))
        if body.decision == "Approved" and r["order_id"]:
            c.execute("UPDATE orders SET refunded=1 WHERE id=?", (r["order_id"],))
        c.commit()
        return row(c.execute("SELECT * FROM refund_requests WHERE id=?", (rid,)).fetchone())
    finally: c.close()
