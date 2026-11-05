import re, html, requests
import os
BASE= os.getenv("ERP_BASE")
MARKS_URL = f"{BASE}/bts/student-list/student-marks"

def submit_project_marks(student_id, marks, remarks,headers ,total_marks, dry_run=True, current_marks=None):
    """Return: success me response json, dry_run me None, error me False
    current_marks optional hai. Dene par agar None nahi hai to student skip hota hai.
    """
    # ---- validation ----
    if current_marks is not None:
        print(f"[SKIP] student {student_id}: marks pehle se lage hain ({current_marks}), nahi bheja")
        return False
    if not isinstance(marks, (int, float)) or isinstance(marks, bool):
        print(f"[SKIP] student {student_id}: marks number hone chahiye, mila {marks!r}")
        return False
    if not (0 <= marks <= total_marks):
        print(f"[SKIP] student {student_id}: marks 0 se {total_marks} ke andar hone chahiye, mila {marks}")
        return False

    text = re.sub(r"\s+", " ", remarks or "").strip()
    if not text:
        print(f"[SKIP] student {student_id}: project me remarks zaroori hain")
        return False

    payload = {"students": [{"id": student_id, "marks": marks, "remarks": f"<p>{html.escape(text)}</p>"}]}
    print("PUT", MARKS_URL)
    print(payload)

    if dry_run:
        print("[DRY RUN] bheja nahi gaya")
        return None

    # ---- request ----
    try:
        r = requests.put(MARKS_URL, headers=headers, json=payload, timeout=30)
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"[ERROR] student {student_id}: network problem ({type(e).__name__}). "
              f"Portal me check karo ki marks lage ya nahi, phir hi dobara chalao.")
        return False
    except Exception as e:
        print(f"[ERROR] student {student_id}: {type(e).__name__}: {e}")
        return False

    print("status:", r.status_code, "|", r.text[:300])

    if r.status_code == 401:
        print("[ERROR] Token expire ho gaya. Naya token lekar `headers` update karo, phir dobara chalao.")
        return False
    if not r.ok:
        print(f"[ERROR] student {student_id}: server ne {r.status_code} diya, marks nahi lage")
        return False

    try:
        return r.json()
    except ValueError:
        print(f"[WARN] student {student_id}: {r.status_code} aaya par response JSON nahi hai, portal me check karo")
        return {"status": r.status_code, "text": r.text[:300]}




def submit_Practical_marks(items,headers, remarks=None, dry_run=True):
    """
    Viva / Theory / Practical (bulk, remarks nahi):
        submit_marks([(465884, 7), (465885, 8)], dry_run=False)

    Project (ek student, marks + remarks):
        submit_marks([(473147, 7)], remarks="Login flow sahi hai.", dry_run=False)
    """
    students = []
    for sid, m in items:
        if not isinstance(m, (int, float)) or isinstance(m, bool):
            raise ValueError(f"student {sid}: marks number hone chahiye, mila {m!r}")
        if m < 0:
            raise ValueError(f"student {sid}: marks negative nahi ho sakte")
        row = {"id": sid, "marks": m}
        if remarks is not None:
            if len(items) != 1:
                raise ValueError("remarks ke saath sirf ek student bhejo (project)")
            text = re.sub(r"\s+", " ", remarks).strip()
            if not text:
                raise ValueError("remarks khaali hain")
            row["remarks"] = f"<p>{html.escape(text)}</p>"
        students.append(row)

    payload = {"students": students}
    print("PUT", MARKS_URL)
    print(payload)

    if dry_run:
        print("[DRY RUN] bheja nahi gaya")
        return None

    r = requests.put(MARKS_URL, headers=headers, json=payload, timeout=30)
    print("status:", r.status_code, "|", r.text[:300])
    r.raise_for_status()
    return r.json()    