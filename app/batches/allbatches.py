
import requests, html, re, time,os
from typing import Annotated
from app.llm.lmsLLM import lmsLLM
from .submit_marks import submit_Practical_marks, submit_project_marks
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.authentication.refreshToken import get_erp_headers
from fastapi.concurrency import run_in_threadpool
ERP_BASE = os.getenv("ERP_BASE")

Batchesrouter = APIRouter(prefix="/batches", tags=["batches"])

AuthCtx = Annotated[dict, Depends(get_erp_headers)]





class RoleBody(BaseModel):
    user_role_id: int          # dependency isi ko userRoleId header banati hai

def formateData(arr):
    
    final=[]
    for v in arr:
        d={"id":v["id"], "name":v["name"], "batches_status":v["batches_status"], "count":v.get("count")}
        final.append(d)
    return final   



@Batchesrouter.post("/batch")
def ongoing(body: RoleBody, ctx: AuthCtx):
    try:
        r = requests.get(
            f"{ERP_BASE}/bts/batches",
            headers=ctx["erp_headers"],
            params={"is_my_batch": "true", "batches_status[]": "ONGOING"},
            timeout=30,
        )


    except requests.RequestException:
        raise HTTPException(status_code=502, detail="ERP abhi available nahi hai")

    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="ERP ne token reject kiya, dobara login karo")
    if r.status_code == 403:
        raise HTTPException(status_code=403, detail="Is role ko ye data dekhne ki permission nahi hai")
    if not r.ok:
        raise HTTPException(status_code=502, detail=f"ERP ne {r.status_code} diya")

    data = r.json()["data"]
    result= data["rows"]
    final= formateData(result)
  

    return {
        "result": final,
        "has_next_page": data["meta"]["hasNextPage"],
        "success": True,
    }
    
# from pydantic import BaseModel




def fetch_pending(batch_id: int, headers: dict) -> list[dict]:
    r = requests.get(
        f"{ERP_BASE}/bts/batches/{batch_id}/batch-wise-student-list",
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()["data"]["rows"]

    pending = []
    for row in rows:
        p = row["pr_vi_ex"]
        if p["mark_null_count"] == 0:
            continue
        for s in p["students"]:
            st = s["student"]
            if st["marks"] is None:
                pending.append({
                    "sheet_id": p["batch_singing_sheet_id"],
                    "project": p["name"],
                    "type": p["type"],
                    "student_id": st["id"],
                    "admission_id": st["admission_id"],
                    "total_marks": st["total_marks"],
                    "link": st["submission_link"],
                })
    return pending

class BatchBody(BaseModel):
    batch_array: list[int]
    user_role_id:int



import uuid
from fastapi import BackgroundTasks

JOBS = {}   # job_id -> status/results (memory mein)


def process_batches(job_id, batch_ids, allbatches, headers):
    job = JOBS[job_id]
    seen = set()                                  # same student+sheet dobara na chale

    for i, pending in enumerate(allbatches):
        rows = _topic_rows(batch_ids[i], headers)
        signing_sheet = None
        desc = None

        for j in pending:
            if not j["link"]:
                job["skipped"] += 1
                continue

            key = (j["student_id"], j["sheet_id"])
            if key in seen:
                continue
            seen.add(key)

            if j["sheet_id"] != signing_sheet:
                desc = get_project_description(rows, j["sheet_id"], j["project"])
                signing_sheet = j["sheet_id"]

            try:
                if not desc or not desc["has_description"]:
                    raise ValueError("project description missing, check skip kiya")

                ans = lmsLLM(j["link"], desc, j["total_marks"])
                marks = ans.marks
                remarks = ans.remarks

                if j["type"] == "EXAM_PRACTICAL":
                    # agar is function ko headers chahiye to yahan pass karo
                    sent = submit_Practical_marks([(j["student_id"], marks)],headers ,dry_run=False)
                else:
                    sent = submit_project_marks(
                        j["student_id"], marks, remarks, headers,
                        j["total_marks"], dry_run=False, current_marks=None,
                    )

                if sent is False:
                    raise RuntimeError("marks portal pe submit nahi hue (terminal log dekho)")

                job["results"].append({
                    "batch_id": batch_ids[i],
                    "sheet_id": j["sheet_id"],
                    "student_id": j["student_id"],
                    "admission_id": j["admission_id"],
                    "marks": marks,
                    "remarks": remarks,
                    "submitted": True,
                })
            except Exception as e:
                job["errors"].append({
                    "student_id": j["student_id"],
                    "error": f"{type(e).__name__}: {e}",
                })
            job["done"] += 1

    job["status"] = "completed"


@Batchesrouter.post("/assignments_check")
async def checkAssignments(ctx: AuthCtx, arr: BatchBody, bg: BackgroundTasks):
    batch_ids = list(dict.fromkeys(arr.batch_array))
    allbatches = []

    for v in batch_ids:
        pending = await run_in_threadpool(fetch_pending, v, ctx["erp_headers"])
        allbatches.append(pending)
    

    total = sum(1 for p in allbatches for j in p if j["link"])
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "running", "total": total, "done": 0,
        "skipped": 0, "results": [], "errors": [],
    }

    bg.add_task(process_batches, job_id, batch_ids, allbatches, ctx["erp_headers"])
    return {"success": True, "job_id": job_id, "total": total}


@Batchesrouter.get("/assignments_check/{job_id}")
async def checkStatus(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job








# _TOPIC_CACHE = {}          # batch_id -> (expires_at, rows), har student pe dobara fetch na ho


def _clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(t))              # HTML tags hatao (Quill editor ka text)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def _norm(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def _topic_rows(batch_id, headers):
    url = f"{ERP_BASE}/bts/batches/{batch_id}/shining-sheet-topic"
    try:
        r = requests.get(url, headers=headers,
                         params={"batch_id": batch_id}, timeout=30)
    except requests.RequestException as e:
        print(f"[ERROR] topics fetch fail ({type(e).__name__})")
        return None
    if not r.ok:
        print(f"[ERROR] topics fetch: status {r.status_code}")
        return None
    try:
        return r.json()["data"]["rows"]
    except (ValueError, KeyError, TypeError):
        print("[ERROR] topics fetch: unexpected response format")
        return None

def get_project_description(rows, sheet_id=None, project_name=None):
    """
    rows         = _topic_rows() ka result (ek batch ke liye, ek baar fetch)
    sheet_id     = student-list ka batch_singing_sheet_id (jaise 418899)
    project_name = student-list ka project name (jaise "To-Do-List")
    Return: {"name", "text", "matched_by", "has_description"} ya None
    """
    if not rows:
        return None
    projects = [x for x in rows if x.get("type") == "PROJECT"]

    match, how = None, None

    # 1) id se match (int/str dono handle)
    if sheet_id is not None:
        want_id = str(sheet_id)
        for x in projects:
            ids = {str(x.get("id"))}
            ids.update(str(s.get("id")) for s in x.get("batchSingingSheets") or [])
            if want_id in ids:
                match, how = x, "id"
                break

    # 2) name se match
    want = _norm(project_name)
    if match is None and want:
        for x in projects:
            if _norm(x.get("name")) == want:
                match, how = x, "name"
                break
        if match is None:
            for x in projects:
                have = _norm(x.get("name"))
                if have and (want in have or have in want):
                    match, how = x, "name (partial)"
                    break

    if match is None:
        print(f"[WARN] project nahi mila (sheet_id={sheet_id}, name={project_name!r}). "
              f"Projects in batch: {[x.get('name') for x in projects]}")
        return None

    parts = [_clean(match.get("description"))]
    for s in match.get("batchSingingSheets") or []:
        parts.append(_clean(s.get("description")))
        parts.append(_clean(s.get("notes")))
    parts = [p for p in dict.fromkeys(parts) if p]      # khaali aur duplicate hatao

    return {
        "name": match.get("name"),
        "text": "\n".join(parts),
        "matched_by": how,
        "has_description": bool(parts),
    }