-- HospRecruit AI Billing System
-- Stripe + Subscription + Usage Management

-- ============================================================================
-- 1. TIER LIMITS CONFIGURATION
-- ============================================================================

CREATE TABLE tier_limits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tier_name VARCHAR(50) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  description TEXT,
  base_price_monthly INT NOT NULL,  -- in cents ($149 = 14900)
  base_price_annual INT NOT NULL,   -- in cents with 20% discount
  roles_per_month INT NOT NULL,     -- max roles can post per month
  video_interviews_per_month INT NOT NULL,
  ai_credits_per_month INT NOT NULL, -- free credits included
  custom_branding BOOLEAN NOT NULL DEFAULT false,
  sso_enabled BOOLEAN NOT NULL DEFAULT false,
  api_access BOOLEAN NOT NULL DEFAULT false,
  priority_support BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert tier configurations
INSERT INTO tier_limits (tier_name, display_name, description, base_price_monthly, base_price_annual, roles_per_month, video_interviews_per_month, ai_credits_per_month, custom_branding, sso_enabled, api_access, priority_support) VALUES
  ('free_trial', 'Free Trial', '14-day trial access', 0, 0, 5, 10, 20, false, false, false, false),
  ('pilot', 'Pilot Program', '$99/month pilot with limited features', 9900, 95040, 10, 25, 50, false, false, false, false),
  ('starter', 'Starter', 'Perfect for small teams', 14900, 143280, 25, 50, 100, false, false, false, false),
  ('growth', 'Growth', 'For growing recruitment teams', 49900, 479040, 100, 250, 500, true, false, false, false),
  ('scale', 'Scale', 'For large-scale operations', 99900, 959040, 500, 1000, 2000, true, true, true, false),
  ('enterprise', 'Enterprise', 'Custom pricing and features', 0, 0, 9999, 9999, 9999, true, true, true, true);

-- ============================================================================
-- 2. ORGANIZATIONS - EXTENDED WITH BILLING
-- ============================================================================

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS (
  tier_name VARCHAR(50) DEFAULT 'free_trial',
  stripe_customer_id VARCHAR(255),
  stripe_subscription_id VARCHAR(255),
  subscription_status VARCHAR(50), -- active, trialing, past_due, canceled, incomplete
  trial_started_at TIMESTAMP,
  trial_ends_at TIMESTAMP,
  billing_cycle_start TIMESTAMP,
  billing_cycle_end TIMESTAMP,
  cancel_at_period_end BOOLEAN DEFAULT false,
  metadata JSONB -- store custom data: max_roles_this_month, etc
);

-- Add foreign key constraint
ALTER TABLE organizations 
ADD CONSTRAINT fk_org_tier 
FOREIGN KEY (tier_name) REFERENCES tier_limits(tier_name);

-- ============================================================================
-- 3. SUBSCRIPTIONS - DETAILED TRACKING
-- ============================================================================

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
  tier_name VARCHAR(50) NOT NULL REFERENCES tier_limits(tier_name),
  
  -- Pricing
  amount_paid INT NOT NULL, -- in cents
  currency VARCHAR(3) DEFAULT 'USD',
  billing_interval VARCHAR(10), -- month or year
  
  -- Status
  status VARCHAR(50) NOT NULL, -- active, trialing, past_due, canceled, incomplete
  started_at TIMESTAMP NOT NULL,
  current_period_start TIMESTAMP NOT NULL,
  current_period_end TIMESTAMP NOT NULL,
  trial_start TIMESTAMP,
  trial_end TIMESTAMP,
  canceled_at TIMESTAMP,
  ended_at TIMESTAMP,
  
  -- Metadata
  auto_renew BOOLEAN DEFAULT true,
  cancel_at_period_end BOOLEAN DEFAULT false,
  payment_method_id VARCHAR(255),
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_org_id ON subscriptions(org_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_stripe_id ON subscriptions(stripe_subscription_id);

-- Trigger to update organization tier
CREATE OR REPLACE FUNCTION update_org_tier_on_subscription_change()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE organizations 
  SET 
    tier_name = NEW.tier_name,
    subscription_status = NEW.status,
    billing_cycle_start = NEW.current_period_start,
    billing_cycle_end = NEW.current_period_end,
    updated_at = NOW()
  WHERE id = NEW.org_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_org_tier_on_subscription
AFTER INSERT OR UPDATE ON subscriptions
FOR EACH ROW
EXECUTE FUNCTION update_org_tier_on_subscription_change();

-- ============================================================================
-- 4. USAGE TRACKING
-- ============================================================================

CREATE TABLE usage_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  
  -- Monthly counters (reset on billing cycle start)
  billing_month DATE NOT NULL, -- first day of month
  roles_created INT DEFAULT 0,
  video_interviews_sent INT DEFAULT 0,
  ai_credits_used INT DEFAULT 0,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(org_id, billing_month)
);

CREATE INDEX idx_usage_org_id ON usage_tracking(org_id);
CREATE INDEX idx_usage_billing_month ON usage_tracking(billing_month);

-- ============================================================================
-- 5. AI CREDITS LEDGER
-- ============================================================================

CREATE TABLE ai_credits_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  
  -- Credit transaction
  transaction_type VARCHAR(50) NOT NULL, -- monthly_grant, purchase, usage, refund
  amount INT NOT NULL, -- in number of credits
  
  -- Reference
  reference_type VARCHAR(50), -- interview_id, invoice_id, etc
  reference_id VARCHAR(255),
  
  -- Details
  description TEXT,
  balance_after INT NOT NULL,
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_credits_org_id ON ai_credits_ledger(org_id);
CREATE INDEX idx_credits_transaction_type ON ai_credits_ledger(transaction_type);
CREATE INDEX idx_credits_created_at ON ai_credits_ledger(created_at);

-- ============================================================================
-- 6. INVOICES
-- ============================================================================

CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  stripe_invoice_id VARCHAR(255) UNIQUE,
  
  -- Amount
  amount_total INT NOT NULL, -- in cents
  amount_paid INT DEFAULT 0,
  amount_due INT DEFAULT 0,
  currency VARCHAR(3) DEFAULT 'USD',
  
  -- Invoice details
  invoice_number VARCHAR(50),
  issue_date TIMESTAMP NOT NULL,
  due_date TIMESTAMP,
  paid_date TIMESTAMP,
  
  -- Status
  status VARCHAR(50) NOT NULL, -- draft, open, void, paid
  description TEXT,
  
  -- Stripe data
  hosted_invoice_url VARCHAR(2048),
  pdf_url VARCHAR(2048),
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_invoices_org_id ON invoices(org_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_paid_date ON invoices(paid_date);

-- ============================================================================
-- 7. PAYMENT METHODS
-- ============================================================================

CREATE TABLE payment_methods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  stripe_payment_method_id VARCHAR(255) UNIQUE NOT NULL,
  
  -- Card details
  card_brand VARCHAR(20), -- visa, mastercard, amex, etc
  card_last4 VARCHAR(4),
  card_exp_month INT,
  card_exp_year INT,
  
  -- Status
  is_default BOOLEAN DEFAULT false,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_payment_methods_org_id ON payment_methods(org_id);

-- ============================================================================
-- 8. BILLING HISTORY & EVENTS
-- ============================================================================

CREATE TABLE billing_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  
  -- Event details
  event_type VARCHAR(100) NOT NULL, -- subscription_created, payment_succeeded, etc
  stripe_event_id VARCHAR(255) UNIQUE,
  
  -- Payload
  event_payload JSONB,
  
  -- Processing
  processed_at TIMESTAMP,
  is_error BOOLEAN DEFAULT false,
  error_message TEXT,
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_billing_events_org_id ON billing_events(org_id);
CREATE INDEX idx_billing_events_type ON billing_events(event_type);
CREATE INDEX idx_billing_events_stripe_id ON billing_events(stripe_event_id);

-- ============================================================================
-- 9. PROMO CODES
-- ============================================================================

CREATE TABLE promo_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(50) UNIQUE NOT NULL,
  
  -- Discount
  discount_type VARCHAR(20), -- percent or fixed
  discount_value INT NOT NULL, -- e.g., 20 for 20% or 9900 for $99
  
  -- Validity
  valid_from TIMESTAMP NOT NULL,
  valid_until TIMESTAMP,
  max_uses INT,
  current_uses INT DEFAULT 0,
  
  -- Restrictions
  applicable_tiers VARCHAR[] DEFAULT ARRAY[]::VARCHAR[], -- empty = all
  description TEXT,
  
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_promo_codes_code ON promo_codes(code);

-- ============================================================================
-- 10. PROMO CODE USAGE TRACKING
-- ============================================================================

CREATE TABLE promo_code_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  promo_code_id UUID NOT NULL REFERENCES promo_codes(id),
  
  amount_discounted INT NOT NULL, -- in cents
  
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_promo_usage_org_id ON promo_code_usage(org_id);

-- ============================================================================
-- 11. ROW LEVEL SECURITY (RLS)
-- ============================================================================

-- Enable RLS on billing tables
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_credits_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_methods ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;

-- RLS Policies - Organization billing data
CREATE POLICY "Users can view own org subscriptions"
  ON subscriptions FOR SELECT
  USING (org_id IN (
    SELECT org_id FROM organizations 
    WHERE id = ANY(
      SELECT DISTINCT organization_id FROM users 
      WHERE id = auth.uid()
    )
  ));

CREATE POLICY "Users can view own org usage"
  ON usage_tracking FOR SELECT
  USING (org_id IN (
    SELECT id FROM organizations 
    WHERE id = ANY(
      SELECT DISTINCT organization_id FROM users 
      WHERE id = auth.uid()
    )
  ));

CREATE POLICY "Users can view own org credits"
  ON ai_credits_ledger FOR SELECT
  USING (org_id IN (
    SELECT id FROM organizations 
    WHERE id = ANY(
      SELECT DISTINCT organization_id FROM users 
      WHERE id = auth.uid()
    )
  ));

CREATE POLICY "Users can view own org invoices"
  ON invoices FOR SELECT
  USING (org_id IN (
    SELECT id FROM organizations 
    WHERE id = ANY(
      SELECT DISTINCT organization_id FROM users 
      WHERE id = auth.uid()
    )
  ));

CREATE POLICY "Users can view own org payment methods"
  ON payment_methods FOR SELECT
  USING (org_id IN (
    SELECT id FROM organizations 
    WHERE id = ANY(
      SELECT DISTINCT organization_id FROM users 
      WHERE id = auth.uid()
    )
  ));

-- ============================================================================
-- 12. HELPER FUNCTIONS
-- ============================================================================

-- Get current billing status for organization
CREATE OR REPLACE FUNCTION get_org_billing_status(org_uuid UUID)
RETURNS TABLE (
  tier_name VARCHAR,
  subscription_status VARCHAR,
  current_period_end TIMESTAMP,
  roles_remaining INT,
  video_interviews_remaining INT,
  ai_credits_remaining INT,
  trial_ends_at TIMESTAMP
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    o.tier_name,
    o.subscription_status,
    s.current_period_end,
    (tl.roles_per_month - COALESCE(ut.roles_created, 0))::INT,
    (tl.video_interviews_per_month - COALESCE(ut.video_interviews_sent, 0))::INT,
    (tl.ai_credits_per_month - COALESCE(ut.ai_credits_used, 0))::INT,
    o.trial_ends_at
  FROM organizations o
  LEFT JOIN tier_limits tl ON o.tier_name = tl.tier_name
  LEFT JOIN subscriptions s ON o.id = s.org_id AND s.status = 'active'
  LEFT JOIN usage_tracking ut ON o.id = ut.org_id 
    AND ut.billing_month = DATE_TRUNC('month', NOW())::DATE
  WHERE o.id = org_uuid;
END;
$$ LANGUAGE plpgsql;

-- Check if org has exceeded tier limits
CREATE OR REPLACE FUNCTION check_tier_limits(
  org_uuid UUID, 
  check_type VARCHAR
)
RETURNS BOOLEAN AS $$
DECLARE
  tier_name_var VARCHAR;
  current_value INT;
  limit_value INT;
BEGIN
  -- Get current tier
  SELECT o.tier_name INTO tier_name_var
  FROM organizations o
  WHERE o.id = org_uuid;
  
  IF check_type = 'roles_per_month' THEN
    SELECT COUNT(*)::INT INTO current_value
    FROM roles
    WHERE organization_id = org_uuid
      AND DATE_TRUNC('month', created_at)::DATE = DATE_TRUNC('month', NOW())::DATE;
    
    SELECT roles_per_month INTO limit_value
    FROM tier_limits
    WHERE tier_name = tier_name_var;
  
  ELSIF check_type = 'video_interviews_per_month' THEN
    SELECT COUNT(*)::INT INTO current_value
    FROM video_interviews
    WHERE organization_id = org_uuid
      AND DATE_TRUNC('month', created_at)::DATE = DATE_TRUNC('month', NOW())::DATE;
    
    SELECT video_interviews_per_month INTO limit_value
    FROM tier_limits
    WHERE tier_name = tier_name_var;
  
  ELSIF check_type = 'ai_credits' THEN
    SELECT COALESCE(ai_credits_used, 0)::INT INTO current_value
    FROM usage_tracking
    WHERE org_id = org_uuid
      AND billing_month = DATE_TRUNC('month', NOW())::DATE;
    
    SELECT ai_credits_per_month INTO limit_value
    FROM tier_limits
    WHERE tier_name = tier_name_var;
  END IF;
  
  RETURN current_value < limit_value;
END;
$$ LANGUAGE plpgsql;

-- Grant credits to org at start of billing cycle
CREATE OR REPLACE FUNCTION grant_monthly_credits(org_uuid UUID)
RETURNS INT AS $$
DECLARE
  tier_name_var VARCHAR;
  credits_to_grant INT;
  new_balance INT;
BEGIN
  SELECT o.tier_name INTO tier_name_var
  FROM organizations o
  WHERE o.id = org_uuid;
  
  SELECT ai_credits_per_month INTO credits_to_grant
  FROM tier_limits
  WHERE tier_name = tier_name_var;
  
  -- Get current balance
  SELECT COALESCE(SUM(amount), 0)::INT INTO new_balance
  FROM ai_credits_ledger
  WHERE org_id = org_uuid;
  
  new_balance := new_balance + credits_to_grant;
  
  -- Add to ledger
  INSERT INTO ai_credits_ledger (
    org_id, transaction_type, amount, description, balance_after
  ) VALUES (
    org_uuid, 'monthly_grant', credits_to_grant, 
    'Monthly credit grant for ' || tier_name_var, new_balance
  );
  
  RETURN new_balance;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 13. INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX idx_tier_limits_tier_name ON tier_limits(tier_name);
CREATE INDEX idx_organizations_stripe_customer_id ON organizations(stripe_customer_id);
CREATE INDEX idx_organizations_tier_name ON organizations(tier_name);
CREATE INDEX idx_organizations_trial_ends_at ON organizations(trial_ends_at);

-- ============================================================================
-- 14. COMMENTS & DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE tier_limits IS 'Defines pricing tiers and their limits';
COMMENT ON TABLE subscriptions IS 'Active Stripe subscriptions and their status';
COMMENT ON TABLE usage_tracking IS 'Monthly usage counters for each organization';
COMMENT ON TABLE ai_credits_ledger IS 'Ledger of all AI credit transactions';
COMMENT ON TABLE invoices IS 'Invoice history and payment tracking';
COMMENT ON TABLE payment_methods IS 'Stored payment methods for each organization';
COMMENT ON TABLE billing_events IS 'Audit trail of all Stripe webhook events';
COMMENT ON TABLE promo_codes IS 'Discount promo codes and their details';
COMMENT ON COLUMN organizations.tier_name IS 'Current subscription tier (free_trial, starter, growth, scale, enterprise)';
COMMENT ON COLUMN organizations.subscription_status IS 'Stripe subscription status (active, trialing, past_due, canceled, incomplete)';
COMMENT ON COLUMN ai_credits_ledger.balance_after IS 'Running balance after this transaction';
