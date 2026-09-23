"""Add public usernames for login and user discovery."""
from alembic import op

revision = "0006_usernames"
down_revision = "0005_chat_messages"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE public.users ADD COLUMN username text;
UPDATE public.users SET username='foodie_'||user_id::text WHERE username IS NULL;
ALTER TABLE public.users ALTER COLUMN username SET NOT NULL;
ALTER TABLE public.users ADD CONSTRAINT users_username_format_check CHECK (
 username ~ '^[a-z0-9][a-z0-9._]{1,28}[a-z0-9_]$' AND position('..' in username)=0
);
CREATE UNIQUE INDEX users_username_lower_uq ON public.users (lower(username));
"""


def upgrade():
    op.get_bind().exec_driver_sql(DDL)


def downgrade():
    raise RuntimeError("Restore into a new isolated database; assigned usernames should not be discarded automatically")
