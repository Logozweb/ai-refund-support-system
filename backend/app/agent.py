import json, re
from datetime import datetime, timezone
from . import llm
from .policy import evaluate, sanitize, REASONS
from .prompts import CLASSIFY_SYSTEM, REVIEW_SYSTEM

TEMPLATES = {
    "approved": "Good news! Your refund of ${amount:.2f} has been approved and will return to your original payment method in 3-5 business days.",
    "approved_partial": "Your refund of ${amount:.2f} has been approved for the eligible items. Final-sale items in the order can't be refunded.",
    "cancelled": "This order was cancelled, so there's nothing to refund. If you were charged, please contact billing.",
    "not_delivered": "This order hasn't been delivered yet, so it isn't eligible for a refund. Once it arrives you can request a return.",
    "already_refunded": "This order has already been refunded, so we can't process another refund for it.",
    "final_sale": "I'm sorry, but final-sale items aren't eligible for refunds unless they arrived damaged or were the wrong item.",
    "window_expired": "I'm sorry, this order is outside our return window, so we can't refund it.",
    "risk_history": "Your request needs a quick review by a human support agent, who will get back to you within 1-2 business days.",
    "high_value": "Refunds of this size are reviewed by a human agent. We'll get back to you within 1-2 business days.",
    "reason_unclear": "Thanks for reaching out. A human agent will review your request and follow up within 1-2 business days.",
    "order_not_found": "I couldn't find that order number. Please check it and try again.",
    "ownership_mismatch": "I couldn't verify that this order belongs to your account. A human agent will review your request.",
    "unknown_customer": "I couldn't verify your account. A human agent will review your request.",
    "security_review": "Your request has been passed to a human agent for review.",
    "ai_conflict": "Thanks for reaching out. A human agent will review your request and follow up within 1-2 business days.",
}
FALLBACK_KEYWORDS = [
    ("incorrect_item", r"wrong (item|product|size|color)|incorrect|different (item|product)|not what i ordered"),
    ("damaged", r"damag|broken|cracked|shattered|smashed|dent"),
    ("defective", r"defect|faulty|doesn'?t work|stopped working|not working|malfunction"),
    ("not_as_described", r"not as described|misleading|different from (the )?(photo|picture|description)"),
    ("changed_mind", r"changed my mind|don'?t (need|want|like)|no longer|too (big|small)|return|refund"),
]
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

def heuristic_classify(msg):
    for reason, pat in FALLBACK_KEYWORDS:
        if re.search(pat, msg, re.I):
            return {"reason": reason, "items_mentioned": [], "summary": "Keyword-based classification (no LLM)."}
    return {"reason": "other", "items_mentioned": [], "summary": "No clear reason found (no LLM)."}

def reply_consistent(reply, decision):
    bad = {"Approved": ["denied", "can't refund", "cannot refund", "not eligible"],
           "Denied": ["approved", "has been issued", "will refund you"],
           "Escalated": ["approved", "has been denied", "has been issued"]}[decision]
    return 20 < len(reply) < 900 and not any(w in reply.lower() for w in bad)

def process(db, req):
    audit = []
    log = lambda step, detail: audit.append({"ts": now(), "step": step, "detail": detail})
    email = req.customer_email.strip().lower()
    msg, heur_flags = sanitize(req.message)
    log("input", f"Received request ({len(msg)} chars). Sanitized; {len(heur_flags)} injection pattern(s) matched.")
    flags = ["prompt_injection_suspected"] if heur_flags else []
    ai_info = {"mode": llm.provider(), "classification": None, "review": None}

    def finish(decision, code, reply, reason=None, order_id=None, amount=0.0, trace=None):
        status = "open" if decision == "Escalated" else "closed"
        cur = db.execute("""INSERT INTO refund_requests(created_at,customer_email,order_id,message,reason,decision,decision_code,
            amount,reply,flags,trace,ai,audit,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now(), email, order_id, msg, reason, decision, code, amount, reply, json.dumps(flags),
             json.dumps(trace or []), json.dumps(ai_info), json.dumps(audit), status))
        db.commit()
        return {"id": cur.lastrowid, "decision": decision, "code": code, "amount": amount, "reply": reply, "flags": flags}

    cust = db.execute("SELECT * FROM customers WHERE lower(email)=?", (email,)).fetchone()
    if not cust:
        flags.append("unknown_customer"); log("identity", "No customer with this email")
        return finish("Escalated", "unknown_customer", TEMPLATES["unknown_customer"])
    m = re.search(r"ORD-\d{4,}", msg, re.I)
    order_id = (req.order_id or (m.group(0) if m else "") or "").upper() or None
    if not order_id:
        return {"decision": "NeedsInfo", "reply": "Which order is this about? Please pick an order or include the order number (e.g. ORD-1001).", "flags": []}
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        log("lookup", f"Order {order_id} not found")
        return finish("Denied", "order_not_found", TEMPLATES["order_not_found"], order_id=order_id)
    if order["customer_id"] != cust["id"]:
        flags.append("ownership_mismatch"); log("lookup", f"Order {order_id} does not belong to {email}")
        return finish("Escalated", "ownership_mismatch", TEMPLATES["ownership_mismatch"], order_id=order_id)
    log("lookup", f"Order {order_id} matched to customer #{cust['id']}")

    # --- AI step 1: classification (untrusted text only, no order data) ---
    try:
        cls = llm.complete_json(CLASSIFY_SYSTEM, f"<customer_message>\n{msg}\n</customer_message>")
        ai_info["classification"] = cls
        log("ai_classify", f"reason={cls.get('reason')}; injection={cls.get('injection_attempt')}")
    except Exception as e:
        cls = heuristic_classify(msg); ai_info["mode"] = "fallback"; ai_info["classification"] = cls
        log("ai_classify", f"LLM unavailable ({type(e).__name__}: {str(e)[:250]}); used keyword fallback")
    reason = cls.get("reason") if isinstance(cls.get("reason"), str) and cls.get("reason") in REASONS else "other"
    if cls.get("injection_attempt") is True and "prompt_injection_suspected" not in flags:
        flags.append("prompt_injection_suspected")

    # --- Deterministic policy ---
    all_items = [dict(r) for r in db.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,))]
    wanted = set(req.item_skus or [])
    mentioned = cls.get("items_mentioned")
    for name in (mentioned if isinstance(mentioned, list) else []):
        n = str(name).lower()
        wanted |= {i["sku"] for i in all_items if n and (n in i["name"].lower() or i["name"].lower() in n)}
    items = [i for i in all_items if i["sku"] in wanted] or all_items
    res = evaluate(dict(cust), dict(order), items, reason)
    decision, code = res["decision"], res["code"]
    log("policy", f"Engine decision={decision} ({code}); amount=${res['amount']}")

    # --- Guardrail: manipulation can never help the customer ---
    if "prompt_injection_suspected" in flags and decision == "Approved":
        decision, code = "Escalated", "security_review"
        res["trace"].append({"rule": "injection_guard", "outcome": "escalate", "note": "Manipulation attempt detected; auto-approval blocked"})
        log("guard", "Approval downgraded to Escalated due to injection attempt")

    # --- AI step 2: sanity review + customer reply (engine decision is fixed) ---
    facts = {"decision": decision, "reason_code": code, "refund_amount": res["amount"], "order_id": order_id,
             "order_status": order["status"], "delivered_date": order["delivered_date"],
             "items": [{"name": i["name"], "price": i["price"], "final_sale": bool(i["final_sale"])} for i in items],
             "policy_trace": res["trace"]}
    reply = TEMPLATES.get(code, TEMPLATES["reason_unclear"]).format(amount=res["amount"])
    try:
        rev = llm.complete_json(REVIEW_SYSTEM, f"<order_facts>\n{json.dumps(facts)}\n</order_facts>\n<customer_message>\n{msg}\n</customer_message>")
        ai_info["review"] = rev
        if rev.get("agrees") is False and decision == "Approved":
            decision, code = "Escalated", "ai_conflict"
            flags.append("ai_flagged_conflict")
            res["trace"].append({"rule": "ai_review", "outcome": "escalate", "note": rev.get("concern", "")})
            log("ai_review", "AI flagged conflict; Approved -> Escalated: " + str(rev.get("concern")))
            reply = TEMPLATES["ai_conflict"]
        else:
            log("ai_review", rev.get("audit_note", "Reviewed"))
            r = str(rev.get("reply", ""))
            if reply_consistent(r, decision):
                reply = r
            else:
                log("ai_reply", "Generated reply failed consistency check; used template")
    except Exception as e:
        log("ai_review", f"LLM unavailable ({type(e).__name__}: {str(e)[:250]}); used template reply")
    return finish(decision, code, reply, reason, order_id, res["amount"], res["trace"])
