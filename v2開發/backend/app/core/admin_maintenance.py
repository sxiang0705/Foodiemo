"""Restricted, audited database maintenance for the email-less first admin."""
import json

from sqlalchemy import text


def reset_email_less_admin_password(connection, username, encoded_password):
    """Reset the sole email-less admin and revoke every credential in the caller's transaction."""
    parts = encoded_password.split("$") if isinstance(encoded_password, str) else []
    if len(parts) != 3 or parts[0] != "scrypt" or not parts[1] or not parts[2]:
        raise ValueError("A scrypt password hash is required")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A username is required")

    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('foodiemo-email-less-admin-reset-v1'))"))
    target = connection.execute(text("""
        SELECT user_id, username FROM public.users
        WHERE lower(username)=lower(:username) AND role='admin'
          AND email IS NULL AND email_auth_exempt=true
        FOR UPDATE
    """), {"username": username.strip()}).mappings().first()
    if not target:
        raise LookupError("No email-less first administrator matches that username")

    revoked_sessions = connection.execute(text("""
        SELECT count(*) FROM public.auth_tokens
        WHERE user_id=:id AND purpose='session'
    """), {"id": target["user_id"]}).scalar()
    revoked_tokens = connection.execute(text("""
        DELETE FROM public.auth_tokens WHERE user_id=:id
    """), {"id": target["user_id"]}).rowcount
    connection.execute(text("""
        UPDATE public.users SET password_hash=:password, updated_at=now()
        WHERE user_id=:id
    """), {"password": encoded_password, "id": target["user_id"]})
    connection.execute(text("""
        INSERT INTO public.admin_audit_logs
            (actor_id,action,target_type,target_id,reason,details)
        VALUES (NULL,'admin.password_reset.offline','user',:id,
                'Offline recovery of email-less first administrator',CAST(:details AS jsonb))
    """), {
        "id": target["user_id"],
        "details": json.dumps({
            "source": "offline_maintenance_tool",
            "revoked_sessions": int(revoked_sessions or 0),
            "revoked_tokens": int(revoked_tokens or 0),
        }),
    })
    return {"user_id": target["user_id"], "username": target["username"],
            "revoked_sessions": int(revoked_sessions or 0)}
