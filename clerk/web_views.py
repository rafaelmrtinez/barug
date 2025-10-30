# web/views/valid_id.py
from __future__ import annotations

import json
import traceback
from typing import Any, Optional, Dict
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.conf import settings

from common.supabase_client import supabase
from common.services.storage import upload_to_storage

EDGE_FN_NAME = "verify-id"

BUCKET_VERIFY = getattr(settings, "SUPABASE_OCR_TEST_BUCKET", "ocr-testing")
BUCKET_FINAL  = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")

# ───────────────── helpers ─────────────────

def _normalize_id_type(value: str) -> str:
    return (
        (value or "").lower()
        .replace("’", "'").replace("'", "")
        .replace(" ", "_").replace("-", "_").strip()
    )

def _ct_from_name(name: str) -> str:
    n = (name or "").lower()
    if n.endswith(".jpg") or n.endswith(".jpeg"): return "image/jpeg"
    if n.endswith(".png"): return "image/png"
    return "image/jpeg"

def _extract_edge_json(res) -> Optional[dict]:
    """
    Accept these shapes from supabase.functions.invoke:
      - bytes (top-level body)
      - {"data": <bytes|string|dict>}
      - object with .data attr
      - string JSON
    """
    # top-level bytes
    if isinstance(res, (bytes, bytearray)):
        try:
            return json.loads(res.decode("utf-8", errors="replace"))
        except Exception:
            return None

    data = None
    if isinstance(res, dict):
        data = res.get("data")
    else:
        data = getattr(res, "data", None)

    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        try:
            return json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            return None
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return None
    if isinstance(res, str):
        try:
            return json.loads(res)
        except Exception:
            return None
    return None

def _json_safe(o: Any) -> Any:
    try:
        json.dumps(o)
        return o
    except TypeError:
        if isinstance(o, dict):
            return {str(k): _json_safe(v) for k, v in o.items()}
        if isinstance(o, (list, tuple, set)):
            t = type(o)
            return t(_json_safe(v) for v in o)
        return repr(o)

# ───────── test page ─────────

@require_http_methods(["GET"])
def upload_valid_id_test_page(request: HttpRequest) -> HttpResponse:
    id_types = [
        ("ephil_id", "ePhilID"),
        ("drivers_license", "Driver's License"),
        ("sss_umid", "SSS/UMID"),
        ("postal_id", "Postal ID"),
    ]
    return render(request, "valid_id_test.html", {"id_types": id_types})

# ───── main API: ocr-testing → Edge → (on PASS) id-uploads ─────

@require_http_methods(["POST"])
def upload_valid_id_files(request: HttpRequest):
    print("=== /clerk/valid-id/upload start ===")
    supabase_uid = (request.POST.get("supabase_uid") or "").strip()
    id_type_in   = (request.POST.get("id_type") or "").strip()
    strict_flag  = (request.POST.get("strict") or "1").strip()
    print(f"[view] inputs uid={supabase_uid!r} id_type={id_type_in!r} strict={strict_flag}")

    if not supabase_uid or not id_type_in:
        print("[view] missing supabase_uid or id_type")
        return JsonResponse({"error": "Missing supabase_uid or id_type."}, status=400)

    front  = request.FILES.get("front")
    back   = request.FILES.get("back")
    selfie = request.FILES.get("selfie")

    def _dbg(f, label):
        if not f: print(f"[view] {label}: MISSING"); return
        try: pos = f.tell()
        except Exception: pos = "?"
        print(f"[view] {label}: name={getattr(f,'name',None)} ct={getattr(f,'content_type',None)} size={getattr(f,'size',None)} pos={pos}")

    _dbg(front, "front"); _dbg(back, "back"); _dbg(selfie, "selfie")
    if not (front and back and selfie):
        return JsonResponse({"error": "front, back, selfie are required files."}, status=400)

    for f in (front, back, selfie):
        try: f.seek(0)
        except Exception: pass

    front_ct = _ct_from_name(getattr(front, "name", "front.jpg"))
    back_ct  = _ct_from_name(getattr(back,  "name", "back.jpg"))
    self_ct  = _ct_from_name(getattr(selfie, "name", "selfie.jpg"))
    print(f"[view] resolved CTs: front={front_ct} back={back_ct} selfie={self_ct}")

    # 1) stage to VERIFY (ocr-testing)
    verify_base = f"person/{supabase_uid}"
    try:
        print("[view] uploading to VERIFY bucket:", BUCKET_VERIFY)
        front_v = upload_to_storage(front,  path=f"{verify_base}/front.jpg",  bucket=BUCKET_VERIFY, upsert=True, make_public=False, reset_metadata=True, content_type=front_ct)
        back_v  = upload_to_storage(back,   path=f"{verify_base}/back.jpg",   bucket=BUCKET_VERIFY, upsert=True, make_public=False, reset_metadata=True, content_type=back_ct)
        self_v  = upload_to_storage(selfie, path=f"{verify_base}/selfie.jpg", bucket=BUCKET_VERIFY, upsert=True, make_public=False, reset_metadata=True, content_type=self_ct)
        print(f"[view] VERIFY uploaded:\n  front={front_v}\n  back={back_v}\n  selfie={self_v}")
    except Exception as e:
        print("[view] upload to VERIFY failed"); traceback.print_exc()
        return JsonResponse({"error": f"Upload to verify bucket failed: {e!s}"}, status=500)

    # 2) call Edge on VERIFY bucket
    body = {
        "person_id": supabase_uid,
        "id_type": _normalize_id_type(id_type_in),
        "bucket": BUCKET_VERIFY,
        "front_path": front_v["path"],
        "back_path":  back_v["path"],
        "selfie_path": self_v["path"],
        "profile_name": (
            getattr(request.user, "get_full_name", lambda: "")() or
            getattr(request.user, "username", "") or
            "Unknown User"
        ),
    }
    print("[view] Edge body:", _json_safe(body))

    try:
        edge_res = supabase.functions.invoke(EDGE_FN_NAME, invoke_options={"body": body})
        print("[view] edge_res RAW type:", type(edge_res).__name__)
        print("[view] edge_res RAW (json-safe):", _json_safe(edge_res))
        edge_data = _extract_edge_json(edge_res)
        print("[view] edge_data PARSED:", _json_safe(edge_data))
    except Exception as e:
        print("[view] Edge function error"); traceback.print_exc()
        try: supabase.storage.from_(BUCKET_VERIFY).remove([front_v["path"], back_v["path"], self_v["path"]])
        except Exception: pass
        return JsonResponse({"error": f"Edge function error: {e!s}"}, status=502)

    if not isinstance(edge_data, dict):
        print("[view] Unexpected edge response → cleaning VERIFY")
        try: supabase.storage.from_(BUCKET_VERIFY).remove([front_v["path"], back_v["path"], self_v["path"]])
        except Exception: pass
        return JsonResponse({"error": "Unexpected edge response."}, status=502)

    passed = (edge_data.get("status") == "PASSED")
    print(f"[view] Edge status: {edge_data.get('status')} (passed={passed})")

    # 3) on PASS → FINAL; else delete VERIFY
    uploaded_final = None
    rpc_result = None

    if passed:
        for f in (front, back, selfie):
            try: f.seek(0)
            except Exception: pass

        final_base = f"person/{supabase_uid}"
        try:
            print("[view] uploading to FINAL bucket:", BUCKET_FINAL)
            front_f = upload_to_storage(front,  path=f"{final_base}/front.jpg",  bucket=BUCKET_FINAL, upsert=True, make_public=True, reset_metadata=True, content_type=front_ct)
            back_f  = upload_to_storage(back,   path=f"{final_base}/back.jpg",   bucket=BUCKET_FINAL, upsert=True, make_public=True, reset_metadata=True, content_type=back_ct)
            self_f  = upload_to_storage(selfie, path=f"{final_base}/selfie.jpg", bucket=BUCKET_FINAL, upsert=True, make_public=True, reset_metadata=True, content_type=self_ct)
            uploaded_final = {"front": front_f, "back": back_f, "selfie": self_f}
            print("[view] FINAL uploaded:", _json_safe(uploaded_final))
        except Exception as e:
            print("[view] upload to FINAL failed"); traceback.print_exc()
            return JsonResponse({"error": f"Upload to final bucket failed: {e!s}", "edge_result": _json_safe(edge_data)}, status=500)

        # optional cleanup
        try:
            print("[view] deleting VERIFY staging files")
            supabase.storage.from_(BUCKET_VERIFY).remove([front_v["path"], back_v["path"], self_v["path"]])
        except Exception as e:
            print(f"[view] delete staging ignored: {e!s}")

        # optional RPC
        try:
            front_url  = front_f.get("public_url") or front_f.get("signed_url")
            back_url   = back_f .get("public_url") or back_f .get("signed_url")
            selfie_url = self_f .get("public_url") or self_f .get("signed_url")
            print("[view] calling RPC insert_valid_id with URLs")
            rpc_result = (
                supabase
                .rpc("insert_valid_id", {
                    "p_person_id": getattr(getattr(request, "profile", None), "person_id", None),
                    "p_valid_id_type_id": None,
                    "p_selfie_path": selfie_url,
                    "p_valid_id_front": front_url,
                    "p_valid_id_back": back_url,
                })
                .execute()
            )
            print("[view] RPC result:", _json_safe(rpc_result))
        except Exception as e:
            print("[view] RPC failed (non-fatal)"); traceback.print_exc()
            rpc_result = {"error": str(e)}
    else:
        try:
            print("[view] verification FAILED — deleting VERIFY staging")
            supabase.storage.from_(BUCKET_VERIFY).remove([front_v["path"], back_v["path"], self_v["path"]])
        except Exception as e:
            print(f"[view] delete staging ignored: {e!s}")

    resp = _json_safe({
        "ok": True,
        "passed": passed,
        "edge_result": edge_data,
        "uploaded_verify": {"front": front_v, "back": back_v, "selfie": self_v},
        "uploaded_final": uploaded_final,
        "rpc_result": rpc_result,
        "verify_bucket": BUCKET_VERIFY,
        "final_bucket": BUCKET_FINAL,
    })

    try:
        print("[view] RESPONSE:", json.dumps(resp, indent=2))
    except Exception:
        print("[view] RESPONSE (fallback str):", str(resp))

    print("=== /clerk/valid-id/upload end ===")
    return JsonResponse(resp, safe=False)
