"""Validated local images, transaction compensation and deferred deletion."""
import io,re,secrets,warnings
from pathlib import Path
from PIL import Image,ImageOps
from fastapi import HTTPException
from sqlalchemy import text
Image.MAX_IMAGE_PIXELS=24000000
def file_path(root,key):
    if not re.fullmatch(r"[a-f0-9]{48}\.jpg",key or ""):raise HTTPException(404,"找不到照片")
    p=(root/key).resolve()
    if p.parent!=root.resolve():raise HTTPException(404,"找不到照片")
    return p
def store_image(request,upload):
    raw=upload.file.read(8*1024*1024+1)
    if not raw or len(raw)>8*1024*1024:raise HTTPException(422,"每張照片最多 8 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in ["JPEG","PNG","WEBP"]:raise ValueError()
                original.load()
                img=ImageOps.exif_transpose(original).convert("RGB")
                img.thumbnail((4096,4096))
                output=io.BytesIO();img.save(output,"JPEG",quality=90)
    except Exception:raise HTTPException(422,"請使用有效的 JPEG、PNG 或 WebP 照片") from None
    root=request.app.state.storage_root
    root.mkdir(parents=True,exist_ok=True)
    key=secrets.token_hex(24)+".jpg";p=file_path(root,key)
    request.state.created_files.append(p)
    with p.open("xb") as f:f.write(output.getvalue())
    return key
def schedule_delete(c,key):
    if key:c.execute(text("INSERT INTO public.file_gc(storage_path) VALUES(:p) ON CONFLICT DO NOTHING"),{"p":key})
def collect_files(app):
    # Physical deletion occurs only AFTER the transaction removing its references committed.
    with app.state.write_engine.begin() as c:
        rows=c.execute(text("SELECT storage_path FROM public.file_gc ORDER BY created_at LIMIT 50 FOR UPDATE SKIP LOCKED")).scalars().all()
        for key in rows:
            used=c.execute(text("SELECT EXISTS(SELECT 1 FROM public.photos WHERE storage_path=:p UNION ALL SELECT 1 FROM public.users WHERE avatar_path=:p)"),{"p":key}).scalar()
            if used:continue
            try:file_path(app.state.storage_root,key).unlink(missing_ok=True)
            except OSError:continue
            c.execute(text("DELETE FROM public.file_gc WHERE storage_path=:p"),{"p":key})
