"""Persist one like per user and record."""
from alembic import op

revision="0003_record_likes"
down_revision="0002_accounts_records"
branch_labels=None
depends_on=None

DDL="""
CREATE TABLE public.record_likes (
 record_id bigint NOT NULL REFERENCES public.records(record_id) ON DELETE CASCADE,
 user_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(record_id,user_id)
);
CREATE INDEX record_likes_user_idx ON public.record_likes(user_id);
"""

def upgrade():
    op.get_bind().exec_driver_sql(DDL)

def downgrade():
    raise RuntimeError("Restore into a new isolated database; likes cannot be discarded automatically")
