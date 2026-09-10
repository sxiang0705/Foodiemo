"""Accounts, verification, preferences and safe file lifecycle for v2."""
from alembic import op
revision="0002_accounts_records"
down_revision="0001_baseline"
branch_labels=None
depends_on=None
DDL="""
ALTER TABLE public.users ADD COLUMN email_verified boolean NOT NULL DEFAULT false;
ALTER TABLE public.users ADD COLUMN avatar_path text;
CREATE UNIQUE INDEX users_email_lower_uq ON public.users (lower(email)) WHERE email IS NOT NULL;
CREATE TABLE public.auth_tokens (
 token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 purpose text NOT NULL CHECK(purpose IN ('session','reset')), expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_tokens_user_idx ON public.auth_tokens(user_id);
CREATE TABLE public.email_challenges (
 user_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 purpose text NOT NULL CHECK(purpose IN ('signup','reset_password')),
 code_hash text NOT NULL, expires_at timestamptz NOT NULL, attempts integer NOT NULL DEFAULT 0,
 sent_at timestamptz NOT NULL DEFAULT now(), window_start timestamptz NOT NULL DEFAULT now(),
 send_count integer NOT NULL DEFAULT 1, PRIMARY KEY(user_id,purpose)
);
CREATE TABLE public.login_limits (
 key_hash text PRIMARY KEY, attempts integer NOT NULL DEFAULT 0,
 window_start timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.user_preferences (
 user_id bigint PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
 version integer NOT NULL, answers jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.file_gc (
 storage_path text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()
);
"""
def upgrade():
    op.get_bind().exec_driver_sql(DDL)
def downgrade():
    raise RuntimeError("Restore into a new isolated database; account/file data cannot be discarded automatically")
