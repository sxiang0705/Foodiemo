import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.accounts import connection
from app.core.security import current_user
from app.core.storage import file_path

router = APIRouter(prefix="/api/admin")


def admin_context(request: Request, c=Depends(connection)):
    actor = current_user(c, request)
    if actor["role"] != "admin":
        raise HTTPException(403, "只有管理員可以使用此功能")
    return {"connection": c, "actor": actor}


def _like(value):
    return "%" + value.strip().replace("/", "//").replace("%", "/%").replace("_", "/_") + "%"


def _email_hint(value):
    if not value or "@" not in value:
        return ""
    name, domain = value.split("@", 1)
    return (name[:1] + "***@" + domain) if name else "***@" + domain


def _audit(c, request, actor, action, target_type, target_id=None, reason="", details=None):
    c.execute(text("""
        INSERT INTO public.admin_audit_logs
            (actor_id,action,target_type,target_id,reason,details,request_id)
        VALUES (:actor,:action,:type,:target,:reason,CAST(:details AS jsonb),:request_id)
    """), {
        "actor": actor["user_id"], "action": action, "type": target_type,
        "target": target_id, "reason": reason[:1000],
        "details": json.dumps(details or {}, ensure_ascii=False),
        "request_id": getattr(request.state, "request_id", None),
    })


def _page(c, sql, params, offset, limit):
    rows = c.execute(text(sql), params | {"offset": offset, "limit": limit}).mappings().all()
    return {"items": [dict(row) for row in rows], "offset": offset, "limit": limit}


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AccountStatus(Reason):
    status: str = Field(pattern="^(active|suspended)$")


class RoleUpdate(Reason):
    role: str = Field(pattern="^(user|admin)$")


class RecordModeration(Reason):
    status: str = Field(pattern="^(visible|hidden)$")


class CommentModeration(Reason):
    hidden: bool


class ReportReview(BaseModel):
    status: str = Field(pattern="^(pending|reviewing|resolved|dismissed)$")
    note: str = Field(default="", max_length=1000)


@router.get("/overview")
def overview(ctx=Depends(admin_context)):
    c = ctx["connection"]
    row = c.execute(text("""
        SELECT
          (SELECT count(*) FROM public.users) AS users,
          (SELECT count(*) FROM public.users WHERE account_status='active') AS active_users,
          (SELECT count(*) FROM public.records) AS posts,
          (SELECT count(*) FROM public.platform_comments WHERE NOT is_deleted AND NOT moderation_hidden) AS comments,
          (SELECT count(*) FROM public.content_reports WHERE status IN ('pending','reviewing')) AS open_reports,
          (SELECT count(*) FROM public.recommendation_runs) AS recommendation_runs,
          (SELECT count(*) FROM public.recommendation_runs WHERE created_at >= now()-interval '7 days') AS recommendation_runs_7d
    """)).mappings().one()
    return dict(row)


@router.get("/users")
def users(q: str = Query("", max_length=80), status: str = Query("", pattern="^(|active|suspended)$"),
          role: str = Query("", pattern="^(|user|admin)$"), offset: int = Query(0, ge=0, le=100000),
          limit: int = Query(25, ge=1, le=100), ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:q='' OR username ILIKE :q ESCAPE '/' OR user_name ILIKE :q ESCAPE '/' OR email ILIKE :q ESCAPE '/') "
    filt += "AND (:status='' OR account_status=:status) AND (:role='' OR role=:role)"
    params = {"q": _like(q) if q.strip() else "", "status": status, "role": role}
    total = c.execute(text("SELECT count(*) FROM public.users " + filt), params).scalar()
    result = _page(c, """
        SELECT user_id::text AS id, username, user_name AS name,
               email_verified, role, account_status,status_reason,status_updated_at,is_premium,
               registration_date, last_login_at
        FROM public.users """ + filt + " ORDER BY registration_date DESC,user_id DESC LIMIT :limit OFFSET :offset",
        params, offset, limit)
    result["total"] = int(total)
    return result


@router.post("/users/{user_id}/status")
def update_user_status(user_id: int, data: AccountStatus, request: Request, ctx=Depends(admin_context)):
    c, actor = ctx["connection"], ctx["actor"]
    if user_id == actor["user_id"] and data.status == "suspended":
        raise HTTPException(422, "不能停用目前登入的管理員帳號")
    c.execute(text("SELECT pg_advisory_xact_lock(hashtext('foodiemo-admin-role-guard-v1'))"))
    target = c.execute(text("SELECT user_id,role,account_status FROM public.users WHERE user_id=:id FOR UPDATE"),
                       {"id": user_id}).mappings().first()
    if not target:
        raise HTTPException(404, "找不到使用者")
    if target["role"] == "admin" and data.status == "suspended":
        other_admins = c.execute(text("SELECT count(*) FROM public.users WHERE role='admin' AND account_status='active' AND user_id<>:id"),
                                 {"id": user_id}).scalar()
        if not other_admins:
            raise HTTPException(409, "至少要保留一位啟用中的管理員")
    c.execute(text("""
        UPDATE public.users SET account_status=:status,status_reason=:reason,
          status_updated_at=now(),status_updated_by=:actor,updated_at=now()
        WHERE user_id=:id
    """), {"status": data.status, "reason": data.reason.strip(), "actor": actor["user_id"], "id": user_id})
    revoked = 0
    if data.status == "suspended":
        revoked = c.execute(text("DELETE FROM public.auth_tokens WHERE user_id=:id AND purpose='session'"),
                            {"id": user_id}).rowcount
    _audit(c, request, actor, "user." + data.status, "user", user_id, data.reason,
           {"previous_status": target["account_status"], "revoked_sessions": revoked})
    return {"status": data.status, "revoked_sessions": revoked}


@router.post("/users/{user_id}/role")
def update_user_role(user_id: int, data: RoleUpdate, request: Request, ctx=Depends(admin_context)):
    c, actor = ctx["connection"], ctx["actor"]
    if user_id == actor["user_id"] and data.role != "admin":
        raise HTTPException(422, "不能在目前工作階段移除自己的管理員權限")
    c.execute(text("SELECT pg_advisory_xact_lock(hashtext('foodiemo-admin-role-guard-v1'))"))
    target = c.execute(text("SELECT user_id,role,email_auth_exempt FROM public.users WHERE user_id=:id FOR UPDATE"),
                       {"id": user_id}).mappings().first()
    if not target:
        raise HTTPException(404, "找不到使用者")
    if target["email_auth_exempt"] and data.role != "admin":
        raise HTTPException(409, "請先設定並驗證 Email，才能移除此管理員的無 Email 登入資格")
    if target["role"] == "admin" and data.role == "user":
        other_admins = c.execute(text("SELECT count(*) FROM public.users WHERE role='admin' AND account_status='active' AND user_id<>:id"),
                                 {"id": user_id}).scalar()
        if not other_admins:
            raise HTTPException(409, "至少要保留一位管理員")
    c.execute(text("UPDATE public.users SET role=:role,updated_at=now() WHERE user_id=:id"),
              {"role": data.role, "id": user_id})
    _audit(c, request, actor, "user.role_changed", "user", user_id, data.reason,
           {"previous_role": target["role"], "role": data.role})
    return {"id": str(user_id), "role": data.role}


@router.get("/posts")
def posts(q: str = Query("", max_length=100), status: str = Query("", pattern="^(|visible|hidden)$"),
          offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100), ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:q='' OR r.text ILIKE :q ESCAPE '/' OR u.username ILIKE :q ESCAPE '/' OR u.user_name ILIKE :q ESCAPE '/' " \
           "OR EXISTS (SELECT 1 FROM public.platform_comments search_cm WHERE search_cm.record_id=r.record_id " \
           "AND NOT search_cm.is_deleted AND search_cm.text ILIKE :q ESCAPE '/')) "
    filt += "AND (:status='' OR r.moderation_status=:status)"
    params = {"q": _like(q) if q.strip() else "", "status": status}
    total = c.execute(text("SELECT count(*) FROM public.records r JOIN public.users u USING(user_id) " + filt), params).scalar()
    result = _page(c, """
        SELECT r.record_id::text AS id,r.user_id::text AS user_id,u.username,u.user_name AS author,
               COALESCE(NULLIF(r.text,''),(SELECT cm.text FROM public.platform_comments cm
                 WHERE cm.record_id=r.record_id AND NOT cm.is_deleted ORDER BY cm.create_time,cm.comment_id LIMIT 1),'') AS caption,
               r.location_text AS location,r.create_time,r.is_public,
               r.moderation_status,r.moderation_reason,
               (SELECT count(*) FROM public.photos p WHERE p.record_id=r.record_id) AS photo_count,
               ARRAY(SELECT p.photo_id::text FROM public.photos p WHERE p.record_id=r.record_id ORDER BY p.sort_order,p.photo_id) AS photo_ids,
               (SELECT count(*) FROM public.record_likes l WHERE l.record_id=r.record_id) AS likes,
               (SELECT count(*) FROM public.platform_comments cm WHERE cm.record_id=r.record_id AND NOT cm.is_deleted AND NOT cm.moderation_hidden) AS comments
        FROM public.records r JOIN public.users u USING(user_id)
    """ + filt + " ORDER BY r.create_time DESC,r.record_id DESC LIMIT :limit OFFSET :offset", params, offset, limit)
    result["total"] = int(total)
    return result


@router.post("/posts/{record_id}/moderation")
def moderate_post(record_id: int, data: RecordModeration, request: Request, ctx=Depends(admin_context)):
    c, actor = ctx["connection"], ctx["actor"]
    row = c.execute(text("""
        UPDATE public.records SET moderation_status=:status,moderation_reason=:reason,
          moderated_at=now(),moderated_by=:actor,updated_at=now()
        WHERE record_id=:id RETURNING record_id,moderation_status
    """), {"status": data.status, "reason": data.reason.strip(), "actor": actor["user_id"], "id": record_id}).mappings().first()
    if not row:
        raise HTTPException(404, "找不到貼文")
    _audit(c, request, actor, "post." + data.status, "record", record_id, data.reason)
    return {"id": str(record_id), "moderation_status": row["moderation_status"]}


@router.get("/photos/{photo_id}")
def admin_photo(photo_id: int, request: Request, ctx=Depends(admin_context)):
    c = ctx["connection"]
    key = c.execute(text("SELECT storage_path FROM public.photos WHERE photo_id=:id"), {"id": photo_id}).scalar()
    if not key:
        raise HTTPException(404, "找不到照片")
    path = file_path(request.app.state.storage_root, key)
    if not path.is_file():
        raise HTTPException(404, "找不到照片")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/comments")
def comments(q: str = Query("", max_length=100), status: str = Query("", pattern="^(|visible|hidden)$"),
             offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100), ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:q='' OR cm.text ILIKE :q ESCAPE '/' OR u.username ILIKE :q ESCAPE '/' OR u.user_name ILIKE :q ESCAPE '/') "
    filt += "AND (:status='' OR (CASE WHEN cm.moderation_hidden THEN 'hidden' ELSE 'visible' END)=:status)"
    params = {"q": _like(q) if q.strip() else "", "status": status}
    total = c.execute(text("SELECT count(*) FROM public.platform_comments cm JOIN public.users u USING(user_id) " + filt), params).scalar()
    result = _page(c, """
        SELECT cm.comment_id::text AS id,cm.record_id::text AS record_id,cm.user_id::text AS user_id,
               u.username,u.user_name AS author,cm.text,cm.create_time,cm.is_deleted,cm.moderation_hidden,
               cm.moderation_reason,cm.moderated_at
        FROM public.platform_comments cm JOIN public.users u USING(user_id)
    """ + filt + " ORDER BY cm.create_time DESC,cm.comment_id DESC LIMIT :limit OFFSET :offset", params, offset, limit)
    result["total"] = int(total)
    return result


@router.post("/comments/{comment_id}/moderation")
def moderate_comment(comment_id: int, data: CommentModeration, request: Request, ctx=Depends(admin_context)):
    c, actor = ctx["connection"], ctx["actor"]
    hidden = data.hidden
    row = c.execute(text("""
        UPDATE public.platform_comments SET moderation_hidden=:hidden,moderation_reason=:reason,
          moderated_at=now(),moderated_by=:actor,updated_at=now()
        WHERE comment_id=:id RETURNING comment_id,moderation_hidden
    """), {"hidden": hidden, "reason": data.reason.strip(), "actor": actor["user_id"], "id": comment_id}).mappings().first()
    if not row:
        raise HTTPException(404, "找不到留言")
    _audit(c, request, actor, "comment." + ("hidden" if hidden else "restored"), "comment", comment_id, data.reason)
    return {"id": str(comment_id), "moderation_hidden": row["moderation_hidden"]}


@router.get("/reports")
def reports(status: str = Query("", pattern="^(|pending|reviewing|resolved|dismissed)$"),
            offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100), ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:status='' OR rp.status=:status)"
    params = {"status": status}
    total = c.execute(text("SELECT count(*) FROM public.content_reports rp " + filt), params).scalar()
    result = _page(c, """
        SELECT rp.report_id::text AS id,rp.reporter_id::text AS reporter_id,
               reporter.username AS reporter_username,rp.target_type,rp.target_id::text AS target_id,
               rp.reason_code,rp.details,rp.status,rp.resolution_note,rp.created_at,rp.updated_at,
               resolver.username AS resolved_by_username,
               CASE rp.target_type
                 WHEN 'record' THEN (SELECT left(COALESCE(NULLIF(r.text,''),(SELECT cm.text FROM public.platform_comments cm
                   WHERE cm.record_id=r.record_id AND NOT cm.is_deleted ORDER BY cm.create_time,cm.comment_id LIMIT 1),''),240)
                   FROM public.records r WHERE r.record_id=rp.target_id)
                 WHEN 'comment' THEN (SELECT left(cm.text,240) FROM public.platform_comments cm WHERE cm.comment_id=rp.target_id)
                 WHEN 'user' THEN (SELECT u.username FROM public.users u WHERE u.user_id=rp.target_id)
               END AS target_summary
               ,CASE rp.target_type
                 WHEN 'record' THEN (SELECT r.moderation_status FROM public.records r WHERE r.record_id=rp.target_id)
                 WHEN 'comment' THEN (SELECT CASE WHEN cm.moderation_hidden THEN 'hidden' ELSE 'visible' END
                   FROM public.platform_comments cm WHERE cm.comment_id=rp.target_id)
                 WHEN 'user' THEN (SELECT u.account_status FROM public.users u WHERE u.user_id=rp.target_id)
               END AS target_status,
               CASE rp.target_type
                 WHEN 'record' THEN (SELECT u.username FROM public.records r JOIN public.users u USING(user_id) WHERE r.record_id=rp.target_id)
                 WHEN 'comment' THEN (SELECT u.username FROM public.platform_comments cm JOIN public.users u USING(user_id) WHERE cm.comment_id=rp.target_id)
                 WHEN 'user' THEN (SELECT u.username FROM public.users u WHERE u.user_id=rp.target_id)
               END AS target_username,
               CASE WHEN rp.target_type='record' THEN ARRAY(
                 SELECT p.photo_id::text FROM public.photos p WHERE p.record_id=rp.target_id ORDER BY p.sort_order,p.photo_id LIMIT 3
               ) ELSE ARRAY[]::text[] END AS target_photo_ids
        FROM public.content_reports rp
        LEFT JOIN public.users reporter ON reporter.user_id=rp.reporter_id
        LEFT JOIN public.users resolver ON resolver.user_id=rp.resolved_by
    """ + filt + " ORDER BY rp.created_at DESC,rp.report_id DESC LIMIT :limit OFFSET :offset", params, offset, limit)
    result["total"] = int(total)
    return result


@router.post("/reports/{report_id}/review")
def review_report(report_id: int, data: ReportReview, request: Request, ctx=Depends(admin_context)):
    c, actor = ctx["connection"], ctx["actor"]
    note = data.note.strip()
    if data.status in {"resolved", "dismissed"} and not note:
        raise HTTPException(422, "結案或駁回案件時請填寫處理說明")
    row = c.execute(text("""
        UPDATE public.content_reports SET status=:status,resolution_note=:note,
          resolved_by=CASE WHEN :final THEN :actor ELSE NULL END,
          resolved_at=CASE WHEN :final THEN now() ELSE NULL END,updated_at=now()
        WHERE report_id=:id RETURNING report_id,status,target_type,target_id
    """), {"status": data.status, "note": note, "final": data.status in {"resolved", "dismissed"},
          "actor": actor["user_id"], "id": report_id}).mappings().first()
    if not row:
        raise HTTPException(404, "找不到檢舉案件")
    _audit(c, request, actor, "report." + data.status, "report", report_id, note,
           {"target_type": row["target_type"], "target_id": str(row["target_id"])})
    return {"id": str(report_id), "status": row["status"]}


@router.get("/recommendations")
def recommendation_runs(version: str = Query("", max_length=80), user_id: int | None = Query(None, ge=1),
                        offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100),
                        ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:version='' OR rr.algorithm_version=:version) AND (:uid IS NULL OR rr.user_id=:uid)"
    params = {"version": version, "uid": user_id}
    total = c.execute(text("SELECT count(*) FROM public.recommendation_runs rr " + filt), params).scalar()
    result = _page(c, """
        SELECT rr.recommendation_run_id::text AS id,rr.user_id::text AS user_id,u.username,
               rr.algorithm_version,rr.request_context,rr.candidate_count,rr.created_at,
               COALESCE((
                 SELECT json_agg(json_build_object(
                   'restaurant_id',ri.restaurant_id::text,'restaurant',rest.title,'rank',ri.rank,
                   'score',ri.score,'reasons',ri.reasons,
                   'impressions',(SELECT count(*) FROM public.user_restaurant_events ev
                     WHERE ev.recommendation_run_id=rr.recommendation_run_id
                       AND ev.restaurant_id=ri.restaurant_id AND ev.event_type='impression'),
                   'detail_opens',(SELECT count(*) FROM public.user_restaurant_events ev
                     WHERE ev.recommendation_run_id=rr.recommendation_run_id
                       AND ev.restaurant_id=ri.restaurant_id AND ev.event_type='open_detail'),
                   'map_opens',(SELECT count(*) FROM public.user_restaurant_events ev
                     WHERE ev.recommendation_run_id=rr.recommendation_run_id
                       AND ev.restaurant_id=ri.restaurant_id AND ev.event_type='open_map')
                 ) ORDER BY ri.rank)
                 FROM public.recommendation_items ri
                 LEFT JOIN public.restaurant_rows rest ON rest.restaurant_id=ri.restaurant_id
                 WHERE ri.recommendation_run_id=rr.recommendation_run_id
               ),'[]'::json) AS items
        FROM public.recommendation_runs rr JOIN public.users u USING(user_id)
    """ + filt + " ORDER BY rr.created_at DESC,rr.recommendation_run_id DESC LIMIT :limit OFFSET :offset", params, offset, limit)
    result["total"] = int(total)
    return result


@router.get("/audit")
def audit_logs(action: str = Query("", max_length=80), offset: int = Query(0, ge=0, le=100000),
               limit: int = Query(50, ge=1, le=100), ctx=Depends(admin_context)):
    c = ctx["connection"]
    filt = "WHERE (:action='' OR a.action=:action)"
    params = {"action": action}
    total = c.execute(text("SELECT count(*) FROM public.admin_audit_logs a " + filt), params).scalar()
    result = _page(c, """
        SELECT a.audit_id::text AS id,
               CASE WHEN a.action='admin.password_reset.offline' THEN '離線維運' ELSE u.username END AS actor_username,
               a.action,a.target_type,
               a.target_id::text AS target_id,a.reason,a.details,a.request_id,a.created_at
        FROM public.admin_audit_logs a LEFT JOIN public.users u ON u.user_id=a.actor_id
    """ + filt + " ORDER BY a.created_at DESC,a.audit_id DESC LIMIT :limit OFFSET :offset", params, offset, limit)
    result["total"] = int(total)
    return result
