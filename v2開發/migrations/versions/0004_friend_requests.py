"""Friend requests and accepted relationships."""
from alembic import op

revision="0004_friend_requests"
down_revision="0003_record_likes"
branch_labels=None
depends_on=None

DDL="""
CREATE TABLE public.friend_requests (
 request_id bigserial PRIMARY KEY,
 requester_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 addressee_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now(),
 responded_at timestamptz,
 CHECK(requester_id<>addressee_id)
);
CREATE INDEX friend_requests_addressee_pending_idx ON public.friend_requests(addressee_id,created_at DESC) WHERE status='pending';
CREATE INDEX friend_requests_requester_pending_idx ON public.friend_requests(requester_id,created_at DESC) WHERE status='pending';
CREATE UNIQUE INDEX friend_requests_pending_pair_uq ON public.friend_requests(LEAST(requester_id,addressee_id),GREATEST(requester_id,addressee_id)) WHERE status='pending';
CREATE UNIQUE INDEX friend_requests_accepted_pair_uq ON public.friend_requests(LEAST(requester_id,addressee_id),GREATEST(requester_id,addressee_id)) WHERE status='accepted';
"""

def upgrade():
    op.get_bind().exec_driver_sql(DDL)

def downgrade():
    raise RuntimeError("Restore into a new isolated database; friend relationships cannot be discarded automatically")
