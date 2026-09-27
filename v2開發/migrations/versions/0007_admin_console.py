"""Add audited moderation, reports, and account status for the admin console."""
from alembic import op

revision = "0007_admin_console"
down_revision = "0006_usernames"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE public.users
 ADD COLUMN account_status text NOT NULL DEFAULT 'active'
   CHECK (account_status IN ('active','suspended')),
 ADD COLUMN status_reason text,
 ADD COLUMN status_updated_at timestamptz NOT NULL DEFAULT now(),
 ADD COLUMN status_updated_by bigint REFERENCES public.users(user_id) ON DELETE SET NULL;

ALTER TABLE public.records
 ADD COLUMN moderation_status text NOT NULL DEFAULT 'visible'
   CHECK (moderation_status IN ('visible','hidden')),
 ADD COLUMN moderation_reason text,
 ADD COLUMN moderated_at timestamptz,
 ADD COLUMN moderated_by bigint REFERENCES public.users(user_id) ON DELETE SET NULL;
CREATE INDEX records_moderation_created_idx
 ON public.records (moderation_status, create_time DESC, record_id DESC);

ALTER TABLE public.platform_comments
 ADD COLUMN moderation_hidden boolean NOT NULL DEFAULT false,
 ADD COLUMN moderation_reason text,
 ADD COLUMN moderated_at timestamptz,
 ADD COLUMN moderated_by bigint REFERENCES public.users(user_id) ON DELETE SET NULL;

CREATE TABLE public.content_reports (
 report_id bigserial PRIMARY KEY,
 reporter_id bigint REFERENCES public.users(user_id) ON DELETE SET NULL,
 target_type text NOT NULL CHECK (target_type IN ('user','record','comment')),
 target_id bigint NOT NULL CHECK (target_id > 0),
 reason_code text NOT NULL CHECK (reason_code IN ('spam','harassment','inappropriate','privacy','other')),
 details text NOT NULL DEFAULT '' CHECK (char_length(details) <= 2000),
 status text NOT NULL DEFAULT 'pending'
   CHECK (status IN ('pending','reviewing','resolved','dismissed')),
 resolution_note text,
 resolved_by bigint REFERENCES public.users(user_id) ON DELETE SET NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 resolved_at timestamptz
);
CREATE INDEX content_reports_status_created_idx
 ON public.content_reports (status, created_at DESC, report_id DESC);
CREATE INDEX content_reports_target_idx
 ON public.content_reports (target_type, target_id, created_at DESC);

CREATE TABLE public.admin_audit_logs (
 audit_id bigserial PRIMARY KEY,
 actor_id bigint REFERENCES public.users(user_id) ON DELETE SET NULL,
 action text NOT NULL CHECK (char_length(action) BETWEEN 1 AND 80),
 target_type text NOT NULL CHECK (char_length(target_type) BETWEEN 1 AND 40),
 target_id bigint,
 reason text NOT NULL DEFAULT '' CHECK (char_length(reason) <= 1000),
 details jsonb NOT NULL DEFAULT '{}'::jsonb,
 request_id text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX admin_audit_created_idx ON public.admin_audit_logs (created_at DESC, audit_id DESC);
CREATE INDEX admin_audit_actor_created_idx ON public.admin_audit_logs (actor_id, created_at DESC);
"""


def upgrade():
    op.get_bind().exec_driver_sql(DDL)


def downgrade():
    raise RuntimeError("Admin audit, moderation, and report data must be preserved; restore into a new database")
