-- Migration: Create demo_requests table for lead capture
-- Created: April 2026

-- Create demo_requests table
CREATE TABLE IF NOT EXISTS demo_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  company_name VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  hiring_volume VARCHAR(50), -- "1-5", "5-10", "10-50", "50+"
  current_pain_points TEXT[], -- ARRAY of selected pain points
  demo_type VARCHAR(50) NOT NULL DEFAULT 'general', -- 'general', 'screening', 'scheduling'
  preferred_time TIMESTAMP,
  timezone VARCHAR(50),
  notes TEXT,
  company_size VARCHAR(50), -- "1-50", "50-200", "200-500", "500+"
  industry VARCHAR(100),
  budget_range VARCHAR(50), -- "Under $500", "$500-$2k", "$2k-$5k", "$5k+"
  status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending', 'scheduled', 'completed', 'no_show', 'disqualified'
  contacted_at TIMESTAMP,
  scheduled_at TIMESTAMP,
  completed_at TIMESTAMP,
  source VARCHAR(100) DEFAULT 'landing_page', -- 'landing_page', 'pricing', 'referral', 'organic'
  utm_source VARCHAR(100),
  utm_medium VARCHAR(100),
  utm_campaign VARCHAR(100),
  utm_content VARCHAR(100),
  visitor_id VARCHAR(255),
  custom_data JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX idx_demo_requests_email ON demo_requests(email);
CREATE INDEX idx_demo_requests_status ON demo_requests(status);
CREATE INDEX idx_demo_requests_created_at ON demo_requests(created_at DESC);
CREATE INDEX idx_demo_requests_company_name ON demo_requests(company_name);
CREATE INDEX idx_demo_requests_user_id ON demo_requests(user_id);
CREATE INDEX idx_demo_requests_preferred_time ON demo_requests(preferred_time);

-- Enable RLS
ALTER TABLE demo_requests ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only view their own demo requests
CREATE POLICY "Users can view own demo requests"
  ON demo_requests FOR SELECT
  USING (auth.uid() = user_id OR EXISTS (
    SELECT 1 FROM organizations WHERE id IN (
      SELECT organization_id FROM organization_members WHERE user_id = auth.uid()
    ) AND is_admin = true
  ));

-- RLS Policy: Anyone can insert their own demo request (lead capture)
CREATE POLICY "Anyone can create demo request"
  ON demo_requests FOR INSERT
  WITH CHECK (true);

-- RLS Policy: Only admins can update demo request status
CREATE POLICY "Admins can update demo requests"
  ON demo_requests FOR UPDATE
  USING (EXISTS (
    SELECT 1 FROM organizations org
    JOIN organization_members om ON org.id = om.organization_id
    WHERE om.user_id = auth.uid() AND om.is_admin = true
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM organizations org
    JOIN organization_members om ON org.id = om.organization_id
    WHERE om.user_id = auth.uid() AND om.is_admin = true
  ));

-- Create trigger to update updated_at
CREATE TRIGGER update_demo_requests_updated_at
  BEFORE UPDATE ON demo_requests
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Create function to get demo request aggregate stats
CREATE OR REPLACE FUNCTION get_demo_stats()
RETURNS TABLE (
  total_requests BIGINT,
  pending_requests BIGINT,
  scheduled_requests BIGINT,
  completed_requests BIGINT,
  no_show_requests BIGINT,
  conversion_rate NUMERIC,
  avg_hiring_volume TEXT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    COUNT(*)::BIGINT,
    COUNT(*) FILTER (WHERE status = 'pending')::BIGINT,
    COUNT(*) FILTER (WHERE status = 'scheduled')::BIGINT,
    COUNT(*) FILTER (WHERE status = 'completed')::BIGINT,
    COUNT(*) FILTER (WHERE status = 'no_show')::BIGINT,
    ROUND(
      COUNT(*) FILTER (WHERE status = 'completed')::NUMERIC / 
      NULLIF(COUNT(*), 0) * 100, 
      2
    ),
    MODE() WITHIN GROUP (ORDER BY hiring_volume) AS avg_hiring_volume
  FROM demo_requests;
END;
$$ LANGUAGE plpgsql;

-- Create function to get demo requests by status with pagination
CREATE OR REPLACE FUNCTION get_demo_requests_by_status(
  p_status VARCHAR DEFAULT NULL,
  p_limit INT DEFAULT 50,
  p_offset INT DEFAULT 0
)
RETURNS TABLE (
  id UUID,
  first_name VARCHAR,
  last_name VARCHAR,
  email VARCHAR,
  company_name VARCHAR,
  phone VARCHAR,
  status VARCHAR,
  created_at TIMESTAMP,
  preferred_time TIMESTAMP,
  hiring_volume VARCHAR
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    dr.id,
    dr.first_name,
    dr.last_name,
    dr.email,
    dr.company_name,
    dr.phone,
    dr.status,
    dr.created_at,
    dr.preferred_time,
    dr.hiring_volume
  FROM demo_requests dr
  WHERE (p_status IS NULL OR dr.status = p_status)
  ORDER BY dr.created_at DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$ LANGUAGE plpgsql;

-- Create function to get prospect fit score (high/medium/low)
CREATE OR REPLACE FUNCTION calculate_prospect_fit_score(
  p_hiring_volume VARCHAR,
  p_company_size VARCHAR,
  p_budget_range VARCHAR
)
RETURNS VARCHAR AS $$
DECLARE
  score INT := 0;
BEGIN
  -- Score based on hiring volume
  score := score + CASE 
    WHEN p_hiring_volume = '50+' THEN 30
    WHEN p_hiring_volume = '10-50' THEN 20
    WHEN p_hiring_volume = '5-10' THEN 10
    WHEN p_hiring_volume = '1-5' THEN 5
    ELSE 0
  END;

  -- Score based on company size
  score := score + CASE
    WHEN p_company_size = '500+' THEN 25
    WHEN p_company_size = '200-500' THEN 20
    WHEN p_company_size = '50-200' THEN 10
    WHEN p_company_size = '1-50' THEN 5
    ELSE 0
  END;

  -- Score based on budget
  score := score + CASE
    WHEN p_budget_range = '$5k+' THEN 25
    WHEN p_budget_range = '$2k-$5k' THEN 20
    WHEN p_budget_range = '$500-$2k' THEN 10
    WHEN p_budget_range = 'Under $500' THEN 5
    ELSE 0
  END;

  -- Return fit grade
  RETURN CASE
    WHEN score >= 70 THEN 'high'
    WHEN score >= 40 THEN 'medium'
    ELSE 'low'
  END;
END;
$$ LANGUAGE plpgsql;

-- Create view for high-fit prospects
CREATE OR REPLACE VIEW high_fit_prospects AS
SELECT
  id,
  first_name,
  last_name,
  email,
  company_name,
  phone,
  hiring_volume,
  company_size,
  budget_range,
  status,
  created_at,
  calculate_prospect_fit_score(hiring_volume, company_size, budget_range) as fit_score
FROM demo_requests
WHERE status IN ('pending', 'scheduled')
ORDER BY created_at DESC;

-- Grant permissions
GRANT SELECT ON demo_requests TO anon, authenticated;
GRANT INSERT ON demo_requests TO anon, authenticated;
GRANT SELECT ON high_fit_prospects TO anon, authenticated;
GRANT SELECT ON FUNCTION get_demo_stats() TO anon, authenticated;
GRANT SELECT ON FUNCTION get_demo_requests_by_status(VARCHAR, INT, INT) TO anon, authenticated;
GRANT SELECT ON FUNCTION calculate_prospect_fit_score(VARCHAR, VARCHAR, VARCHAR) TO anon, authenticated;

-- Add comment for documentation
COMMENT ON TABLE demo_requests IS 'Stores demo/audit request leads from landing page';
COMMENT ON COLUMN demo_requests.status IS 'pending, scheduled, completed, no_show, disqualified';
COMMENT ON COLUMN demo_requests.source IS 'Where the lead came from: landing_page, pricing, referral, organic';
