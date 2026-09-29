"""Deterministic refund policy engine. The LLM never overrides this; it can only make outcomes stricter."""
import re
from datetime import date

DEFECT_REASONS = {"damaged", "incorrect_item", "defective", "not_as_described"}
FINAL_SALE_EXEMPT = {"damaged", "incorrect_item"}
STANDARD_DAYS, DEFECT_DAYS, REVIEW_LIMIT = 30, 45, 500.0
REASONS = DEFECT_REASONS | {"changed_mind", "other"}

INJECTION_PATTERNS = [
    r"ignore (all |any |your )?(previous|prior|above|earlier)",
    r"system prompt|developer message|your instructions",
    r"you are now|pretend (to be|you)|act as (an? )?(admin|manager|supervisor|agent|system)",
    r"developer mode|jailbreak|\bdan mode\b",
    r"(override|bypass|disable|skip|ignore).{0,25}(policy|rules?|checks?|review|limit)",
    r"(auto[- ]?)?approve (this|my|the|it)\b",
    r"reveal .{0,25}(instructions|prompt|rules)",
    r"</?\s*(system|assistant|customer_message|instructions?)\s*>",
    r"\{\s*\"?(decision|approved)\"?\s*:",
]

def sanitize(text):
    """Strip control chars, cap length, defang angle brackets (so input cannot close our XML delimiters)."""
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text or "")[:2000].strip()
    flagged = [p for p in INJECTION_PATTERNS if re.search(p, t, re.I)]
    return t.replace("<", "‹").replace(">", "›"), flagged

def evaluate(customer, order, items, reason, today=None):
    today, trace = today or date.today(), []
    t = lambda rule, outcome, note: trace.append({"rule": rule, "outcome": outcome, "note": note})
    def out(decision, code, amount=0.0, refundable=()):
        return {"decision": decision, "code": code, "amount": round(amount, 2),
                "refundable_skus": [i["sku"] for i in refundable], "trace": trace}

    if order["status"] == "cancelled":
        t("order_status", "fail", "Order was cancelled"); return out("Denied", "cancelled")
    if order["status"] != "delivered":
        t("order_status", "fail", f"Order not delivered (status={order['status']})"); return out("Denied", "not_delivered")
    t("order_status", "pass", "Order delivered")
    if order["refunded"]:
        t("already_refunded", "fail", "Order already refunded"); return out("Denied", "already_refunded")
    t("already_refunded", "pass", "No prior refund")

    refundable = [i for i in items if not i["final_sale"] or reason in FINAL_SALE_EXEMPT]
    blocked = [i["name"] for i in items if i not in refundable]
    if blocked:
        t("final_sale", "fail", "Final sale, not eligible: " + ", ".join(blocked))
        if not refundable:
            return out("Denied", "final_sale")
    else:
        t("final_sale", "pass", "No ineligible final-sale items")

    days = (today - date.fromisoformat(order["delivered_date"])).days
    limit = DEFECT_DAYS if reason in DEFECT_REASONS else STANDARD_DAYS
    if days > limit:
        t("return_window", "fail", f"{days} days since delivery > {limit}-day limit"); return out("Denied", "window_expired")
    t("return_window", "pass", f"{days} days since delivery <= {limit}-day limit")

    amount = sum(i["price"] * i["qty"] for i in refundable)
    if customer["refunds_90d"] >= 3 or customer["damage_claims_12m"] >= 3:
        t("risk_history", "escalate", f"{customer['refunds_90d']} refunds/90d, {customer['damage_claims_12m']} damage claims/12m")
        return out("Escalated", "risk_history", amount, refundable)
    t("risk_history", "pass", "Customer history within limits")
    if amount > REVIEW_LIMIT:
        t("high_value", "escalate", f"${amount:.2f} exceeds ${REVIEW_LIMIT:.0f} review threshold")
        return out("Escalated", "high_value", amount, refundable)
    t("high_value", "pass", f"${amount:.2f} within auto-approval limit")
    if reason == "other":
        t("reason", "escalate", "Reason unclear, needs a human"); return out("Escalated", "reason_unclear", amount, refundable)
    t("reason", "pass", f"Reason '{reason}' is eligible")
    return out("Approved", "approved" if not blocked else "approved_partial", amount, refundable)
