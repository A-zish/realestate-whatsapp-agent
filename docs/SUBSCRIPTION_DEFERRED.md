# Subscription model (deferred)

**Do not implement Razorpay until ≥2 pilot builders would pay.**

## Planned fields (accounts)

- `plan` — e.g. `pilot` | `qualify` | `team`
- `pilot_ends_at` — timestamptz
- `billing_status` — e.g. `trial` | `active` | `past_due` | `canceled`

## Planned products (indicative)

| Plan | Who | Indicative INR / month |
|---|---|---|
| Qualify | 1 project, 1 city | 8–15k |
| Team | Multi-project | 25–40k |
| WhatsApp add-on | Real WABA only | +10–20k |

Invoice entity: **Ramatech**. Product name: **LeadPilot**.

## Build order (when unlocked)

1. Alembic columns + gate soft limits (conversations / month).
2. Razorpay checkout + webhook (signature verified).
3. Admin: mark account paid / extend pilot.
4. Soft-block over-limit with upgrade CTA (no hard data delete).

## Explicitly out of scope now

Checkout UI, invoices PDF, GST e-invoicing automation, seats matrix.

See also: `docs/PILOT_RUNBOOK.md` §5, `docs/PILOT_GTM_LEAD_LINK.md` success gate.
