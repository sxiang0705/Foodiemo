"""Private messages between accepted friends."""
from alembic import op

revision = "0005_chat_messages"
down_revision = "0004_friend_requests"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE public.chat_messages (
 message_id bigserial PRIMARY KEY,
 sender_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 recipient_id bigint NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
 body text NOT NULL CHECK (char_length(btrim(body)) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (sender_id<>recipient_id)
);
CREATE INDEX chat_messages_conversation_idx
 ON public.chat_messages (LEAST(sender_id,recipient_id), GREATEST(sender_id,recipient_id), created_at, message_id);
CREATE INDEX chat_messages_recipient_idx ON public.chat_messages(recipient_id,created_at DESC,message_id DESC);
"""


def upgrade():
    op.get_bind().exec_driver_sql(DDL)


def downgrade():
    raise RuntimeError("Restore into a new isolated database; chat history cannot be discarded automatically")
