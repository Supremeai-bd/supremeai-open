-- SupremeAI 2.0 — Migration 06: Referral System
-- Run this after 05_seed_github_repos.sql

-- Referral codes table
CREATE TABLE IF NOT EXISTS referral_codes (
    code TEXT PRIMARY KEY,
    referrer_id TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'expired', 'disabled')),
    redeemed_count INTEGER DEFAULT 0,
    fraud_score DECIMAL(4,2) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '30 days'),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_referral_codes_referrer ON referral_codes(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referral_codes_status ON referral_codes(status);

-- Referral redemptions
CREATE TABLE IF NOT EXISTS referral_redemptions (
    id BIGSERIAL PRIMARY KEY,
    code TEXT REFERENCES referral_codes(code),
    referrer_id TEXT NOT NULL,
    new_user_id TEXT NOT NULL,
    reward_amount DECIMAL(10,2) DEFAULT 0,
    credits_awarded INTEGER DEFAULT 0,
    platform TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_redemptions_referrer ON referral_redemptions(referrer_id);
CREATE INDEX IF NOT EXISTS idx_redemptions_new_user ON referral_redemptions(new_user_id);

-- Credit wallets
CREATE TABLE IF NOT EXISTS credit_wallets (
    user_id TEXT PRIMARY KEY,
    balance DECIMAL(10,2) DEFAULT 0.0,
    lifetime_earned DECIMAL(10,2) DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Credit ledger (append-only)
CREATE TABLE IF NOT EXISTS credit_ledger (
    tx_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason TEXT,
    balance_after DECIMAL(10,2),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_user ON credit_ledger(user_id);

-- Enable Row Level Security (RLS)
ALTER TABLE referral_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_redemptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;
