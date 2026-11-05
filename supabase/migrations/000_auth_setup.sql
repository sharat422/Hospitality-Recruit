-- ============================================================================
-- HospRecruit AI — Auth Setup (complete reset)
-- Paste this entire file into Supabase → SQL Editor and click Run.
-- Safe to run multiple times.
-- ============================================================================

-- 1. Drop any existing broken triggers / functions
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;

-- 2. Tables
CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    industry    VARCHAR(100) DEFAULT 'hospitality',
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id      UUID REFERENCES organizations(id),
    email       VARCHAR(255),
    full_name   VARCHAR(255),
    role        VARCHAR(50) DEFAULT 'hiring_manager',
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- 3. RLS
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_own_row ON users;
CREATE POLICY users_own_row ON users USING (auth.uid() = id);

DROP POLICY IF EXISTS orgs_own ON organizations;
CREATE POLICY orgs_own ON organizations
    USING (id IN (SELECT org_id FROM users WHERE id = auth.uid()));

-- 4. Trigger function — bulletproof: never blocks auth even if insert fails
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    new_org_id UUID;
BEGIN
    BEGIN
        INSERT INTO public.organizations (name, industry)
        VALUES (split_part(NEW.email, '@', 2), 'hospitality')
        RETURNING id INTO new_org_id;

        INSERT INTO public.users (id, org_id, email, full_name)
        VALUES (
            NEW.id,
            new_org_id,
            NEW.email,
            COALESCE(NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1))
        );
    EXCEPTION WHEN OTHERS THEN
        NULL; -- never block signup
    END;
    RETURN NEW;
END;
$$;

-- 5. Attach trigger
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
