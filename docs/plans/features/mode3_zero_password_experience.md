---
id: mode3-zero-password-experience
subject: "Mode 3 Zero-Password Customer Experience"
document_role: architecture
planning_authority: Customer Experience Circle + Security Circle
status: proposed
target_scope: customer_facing
canonical: candidate
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
depends_on:
  - docs/plans/features/customer_api_spec.md
  - docs/plans/architecture/browser_automation.md
  - docs/plans/features/antihacking_security_defense_framework.md
implements:
  - Zero-password session-only authentication for end-users
  - Ephemeral credential lifecycle with automatic expiry
  - Customer-facing login flow without persistent secrets
supersedes: []
superseded_by: []
---

# Mode 3 Zero-Password Customer Experience

**Status:** proposed  
**Scope:** Customer authentication experience requiring zero persistent password storage

---

## 1. Purpose

Deliver a frictionless, zero-password authentication experience for end-users. Mode 3 eliminates persistent credential storage on the platform, reducing breach impact to session lifetime only.

---

## 2. Authentication Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| Mode 1 | API Key + Secret | Machine-to-machine, CI/CD |
| Mode 2 | OAuth2 Authorization Code | Third-party integrations |
| **Mode 3** | **Session-Only Ephemeral** | **End-user browser sessions, zero passwords stored** |

---

## 3. Mode 3 Flow

```text
Customer opens app
        ↓
System generates ephemeral session token (JWT, 15min TTL)
        ↓
Token stored in HttpOnly Secure SameSite cookie
        ↓
No password, no secret, no persistent credential
        ↓
On expiry → silent refresh or re-auth prompt
```

---

## 4. Security Guarantees

- **Zero persistent credential storage:** No password hashes, no API secrets for end-users
- **Automatic expiry:** Sessions expire after 15 minutes of inactivity
- **Device fingerprinting:** Optional secondary factor for suspicious logins
- **Revocation:** Single-click session kill from customer dashboard

---

## 5. Frontend Requirements

- Zero-complexity login: "Continue with email link" or "Continue with Google"
- No password fields in customer-facing UI
- Visible session expiry countdown
- One-click "Log out everywhere" in account settings

---

## 6. Acceptance Criteria

- [ ] End-to-end Mode 3 flow tested in staging
- [ ] No customer password fields in frontend codebase
- [ ] Session revocation propagates to all active connections within 5 seconds
- [ ] Penetration test confirms zero credential persistence after logout

---

## 7. Out of Scope

- Admin credential management (Layer 1 concern)
- API key rotation for machine clients (Mode 1/2)
- Enterprise SSO/SAML integration
