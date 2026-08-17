# Production WhatsApp (Meta WABA) — when ready

Use this **after** a builder (or Ramatech) has Meta Business verification + WhatsApp Business Account. Until then, use the web lead link.

## Prerequisites

1. Meta Business Manager verified (GST / address docs as Meta requests).
2. Phone number **not** logged into consumer WhatsApp.
3. Twilio → Messaging → Senders → WhatsApp Senders → register sender, display name = agency.
4. Content Template approved for opener, e.g.  
   `Hi {{1}}, this is {{2}}. Are you looking to buy or rent a property? Reply YES.`
5. Live app on HTTPS with `PUBLIC_BASE_URL` set.

## LeadPilot configuration

1. Channels → WhatsApp: Account SID, Auth Token, **production From**, **approved ContentSid (HX…)**.
2. Twilio Console → WhatsApp sender / sandbox settings:  
   When a message comes in → `POST {PUBLIC_BASE_URL}/webhook`
3. Send test to one real handset; confirm chat shows **builder display name**, not Twilio Trial.
4. Openers: max 10; template variables map to `{"1": name, "2": agency_name}` in code.

## Inbound AI

- Inside 24h of lead reply: app returns TwiML free text from `run_conversation_turn` (Groq).
- Outside 24h: WhatsApp requires another template — do not expect free-text openers.

## Code touchpoints

- `app/twilio_client.py` — ContentSid vs Body
- `app/main.py` — `/webhook`, `/dashboard/send-openers`
- `app/twilio_verify.py` — signature check using public URL

## Not done until WABA exists

Do not switch the pilot pitch to WhatsApp-first. This doc is the ops checklist for Phase C.
