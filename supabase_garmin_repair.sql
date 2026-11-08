-- Apex personal deployment: complete the constraints/policies required by data_store.py.
-- Run in Supabase SQL Editor after checking that no duplicate (user_id, date) rows exist.

-- 1) The application upserts daily metrics with on_conflict="user_id,date".
-- This unique index is REQUIRED for those upserts to work.
CREATE UNIQUE INDEX IF NOT EXISTS daily_telemetry_user_date_uidx
    ON public.daily_telemetry (user_id, date);

-- 2) The migration enables RLS, but enabling RLS alone does not grant access.
-- Create an owner-only policy if an equivalent policy is not already present.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'daily_telemetry'
          AND policyname = 'apex_user_owns_rows'
    ) THEN
        CREATE POLICY apex_user_owns_rows ON public.daily_telemetry
            FOR ALL TO authenticated
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'training_sessions'
          AND policyname = 'apex_user_owns_rows'
    ) THEN
        CREATE POLICY apex_user_owns_rows ON public.training_sessions
            FOR ALL TO authenticated
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

-- 3) Ensure authenticated users can use the tables through Supabase's API.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.daily_telemetry TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.training_sessions TO authenticated;
