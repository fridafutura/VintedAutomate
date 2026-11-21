"""Decide how to respond to an incoming buyer message.

Important design choice: the LLM classifies intent and drafts phrasing, but
it never invents the discount number. The actual price/discount decision
always comes from `discounts.py`. The LLM is only told the already-decided
number and asked to phrase a natural reply around it.
"""

from __future__ import annotations

from .claude_client import ClaudeClient
from .config import BusinessRules, DEFAULT_RULES
from .discounts import evaluate_discount_request
from .models import AgentDecision, IncomingMessage, Listing

_CLASSIFY_SYSTEM_PROMPT = """\
Du analysierst eine Käufer-Nachricht zu einem Vinted-Angebot. Dir liegt die
vollständige Artikelbeschreibung vor. Antworte NUR mit einem JSON-Objekt:

{
  "intent": "question" | "discount_request" | "other",
  "requested_discount_rate": Zahl zwischen 0 und 1, oder null,
  "requested_price_eur": Zahl, oder null,
  "can_answer_confidently": true/false,
  "draft_reply": "Antwortvorschlag auf die Frage, oder null bei discount_request/other",
  "escalation_reason": "falls can_answer_confidently=false: kurzer Grund, sonst null"
}

Setze can_answer_confidently nur auf true, wenn die Artikelbeschreibung die Antwort
wirklich enthält oder du sie offensichtlich aus den Fotos/Notizen ableiten kannst.
Erfinde nichts (z.B. Maße, die nicht angegeben sind) - dann lieber escalieren.
Bei "discount_request": extrahiere die Zahl, falls der Käufer einen konkreten Rabatt
oder Preis genannt hat (z.B. "15% weniger?" -> requested_discount_rate 0.15,
"geht's für 10€?" -> requested_price_eur 10). Wenn kein konkreter Wert genannt wurde
(z.B. nur "Rabatt?" oder "günstiger?"), lass beide Felder null.
"""

_PHRASE_DISCOUNT_SYSTEM_PROMPT = """\
Formuliere eine kurze, freundliche Vinted-Nachricht auf Deutsch an den Käufer,
die genau diesen bereits entschiedenen Rabatt kommuniziert. Erfinde keine
zusätzlichen Zusagen oder Zahlen. Keine Anrede/Signatur, nur der Nachrichtentext.
"""


def handle_incoming_message(
    listing: Listing,
    message: IncomingMessage,
    claude: ClaudeClient,
    rules: BusinessRules = DEFAULT_RULES,
    already_offered_rate: float = 0.0,
) -> AgentDecision:
    fields = listing.fields
    context = (
        f"Artikel: {fields.title}\n"
        f"Beschreibung: {fields.description}\n"
        f"Marke: {fields.brand}, Größe: {fields.size}, Farbe: {fields.color}, "
        f"Zustand: {fields.condition.value}, Material: {fields.material}\n"
        f"Bekannte Mängel: {', '.join(fields.flaws_disclosed) or 'keine'}\n"
        f"Aktueller Preis: {fields.price_eur:.2f} €\n\n"
        f"Käufer-Nachricht: {message.text}"
    )

    classification = claude.structured_request(
        system=_CLASSIFY_SYSTEM_PROMPT,
        user_text=context,
    )

    intent = classification.get("intent", "other")

    if intent == "discount_request":
        requested_rate = classification.get("requested_discount_rate")
        requested_price = classification.get("requested_price_eur")

        if requested_rate is None and requested_price is None:
            # No concrete number from the buyer: treat like the standard
            # "like" discount as the opening offer, but never *less* than
            # whatever was already offered earlier in this conversation.
            requested_rate = max(rules.like_discount_rate, already_offered_rate)

        decision = evaluate_discount_request(
            current_price_eur=fields.price_eur,
            rules=rules,
            requested_rate=requested_rate,
            requested_price_eur=requested_price if requested_rate is None else None,
        )

        if decision.escalate:
            return AgentDecision(
                auto_reply_text=None,
                discount_offered_rate=None,
                escalate_to_seller=True,
                escalation_reason=decision.reason,
            )

        reply = claude.text_request(
            system=_PHRASE_DISCOUNT_SYSTEM_PROMPT,
            user_text=(
                f"Käufer-Nachricht: {message.text}\n"
                f"Entschiedener Preis: {decision.offered_price_eur:.2f} € "
                f"(statt {fields.price_eur:.2f} €, entspricht ca. "
                f"{decision.offered_rate:.0%} Rabatt). Grund intern: {decision.reason}"
            ),
        )
        return AgentDecision(
            auto_reply_text=reply,
            discount_offered_rate=decision.offered_rate,
            escalate_to_seller=False,
        )

    if intent == "question":
        if classification.get("can_answer_confidently"):
            return AgentDecision(
                auto_reply_text=classification.get("draft_reply"),
                discount_offered_rate=None,
                escalate_to_seller=False,
            )
        return AgentDecision(
            auto_reply_text=None,
            discount_offered_rate=None,
            escalate_to_seller=True,
            escalation_reason=classification.get("escalation_reason") or "Frage kann nicht sicher beantwortet werden.",
        )

    # "other": small talk etc. - reply if we have a draft, otherwise escalate.
    draft = classification.get("draft_reply")
    if draft:
        return AgentDecision(auto_reply_text=draft, discount_offered_rate=None, escalate_to_seller=False)
    return AgentDecision(
        auto_reply_text=None,
        discount_offered_rate=None,
        escalate_to_seller=True,
        escalation_reason="Nachricht konnte nicht eindeutig eingeordnet werden.",
    )
