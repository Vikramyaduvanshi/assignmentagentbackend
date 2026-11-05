"""
token_dependency.py
Dependency: cookies se token leke ERP ke liye ready token + headers return karta hai.

Dono cases handle hote hain:
  - access_token cookie me nahi hai       -> refresh_token se naya access token (Cognito), cookie update
  - access_token expire ho gaya hai       -> refresh_token se naya access token (Cognito), cookie update
  - dono hi nahi / refresh bhi expire     -> 401 (dobara login)

(Refresh token khud ERP ko nahi bheja ja sakta, wo encrypted hota hai. Isliye ek chhoti Cognito call
 se naya access token liya jata hai, wo bhi sirf tab jab zaroorat ho.)

userRoleId:
  - sirf request body ke `user_role_id` key se (JSON body). Cookie ya header se nahi liya jata.
  - body me "profile" key ho (value kuch bhi) to user_role_id ke bina bhi chalega (profile jaisi calls ke liye).
    Agar user_role_id bhi saath diya ho to userRoleId header phir bhi lag jata hai.

Token ki signature yahan verify nahi hoti (ERP khud karta hai). Ye sirf token pass karne ke liye hai,
apne routes ki security isse mat banao.

Use:
  from app.authentication.token_dependency import get_erp_headers, get_erp_headers_no_role

  class MarksBody(BaseModel):
      user_role_id: int
      student_id: int
      marks: int

  @router.put("/marks")
  def submit(body: MarksBody, ctx: dict = Depends(get_erp_headers)):
      r = requests.put(f"{ERP_BASE}/bts/student-list/student-marks", headers=ctx["erp_headers"], json={...}, timeout=30)

  @router.get("/profile")          # role ki zarurat nahi
  def profile(ctx: dict = Depends(get_erp_headers_no_role)):
      ...

Return format (dono dependencies ka): {"access_token": token, "erp_headers": headers}
"""

import base64
import json
import logging
import os
import time

import requests
from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

log = logging.getLogger("auth")

CLIENT_ID = os.getenv("client_id")
REGION = os.getenv("pool_region")
if not CLIENT_ID or not REGION:
    raise RuntimeError("env variable client_id / pool_region set nahi hai (load_dotenv() pehle chalao)")

COGNITO_URL = f"https://cognito-idp.{REGION}.amazonaws.com/"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"   # production (HTTPS) me true
EXPIRY_BUFFER = 30   # seconds: expire hone se 30 sec pehle hi naya le lo


def _seconds_left(token: str) -> float:
    """JWT ke `exp` se bacha hua time. Token kharab ho to 0."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))["exp"] - time.time()
    except Exception:
        return 0


def _exchange_refresh_token(refresh_token: str) -> dict:
    """blocking call, isliye threadpool me chalayi jati hai"""
    try:
        r = requests.post(
            COGNITO_URL,
            headers={"X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
                     "Content-Type": "application/x-amz-json-1.1"},
            json={"AuthFlow": "REFRESH_TOKEN_AUTH", "ClientId": CLIENT_ID,
                  "AuthParameters": {"REFRESH_TOKEN": refresh_token}},
            timeout=15,
        )
    except requests.RequestException as e:
        log.error("refresh network error: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Auth service abhi available nahi hai")

    if r.status_code == 400:                     # refresh token expire / revoke
        raise HTTPException(status_code=401, detail="Session expired, dobara login karo")
    if not r.ok:
        raise HTTPException(status_code=502, detail="Token refresh nahi ho paya")
    return r.json()["AuthenticationResult"]


async def _read_body(request: Request) -> dict:
    """JSON body dict ke roop me. Body nahi / JSON nahi / dict nahi to {}."""
    if not (request.headers.get("content-type") or "").startswith("application/json"):
        return {}
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def _resolve(request: Request, response: Response, require_role: bool) -> dict:
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    # ---- token: cookie valid ho to wahi, warna refresh se naya ----
    if access_token and _seconds_left(access_token) > EXPIRY_BUFFER:
        token = access_token
    else:
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Please login again")
        result = await run_in_threadpool(_exchange_refresh_token, refresh_token)
        token = result["AccessToken"]
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=result.get("ExpiresIn", 3600),
        )

    headers = {"Authorization": token, "Accept": "application/json"}

    # ---- role ----
    body = await _read_body(request)
    role = body.get("user_role_id")
    is_profile_call = "profile" in body             # body me "profile" key ho (value kuch bhi) to role zaroori nahi

    if role in (None, ""):
        if require_role and not is_profile_call:
            raise HTTPException(status_code=400, detail="user_role_id request body me bhejo")
    else:
        if not str(role).isdigit():
            raise HTTPException(status_code=400, detail="user_role_id number hona chahiye")
        headers["userRoleId"] = str(role)

    return {"access_token": token, "erp_headers": headers}


async def get_erp_headers(request: Request, response: Response) -> dict:
    """token + userRoleId (zaroori)"""
    return await _resolve(request, response, require_role=True)


async def get_erp_headers_no_role(request: Request, response: Response) -> dict:
    """token (+ userRoleId agar diya ho), role zaroori nahi"""
    return await _resolve(request, response, require_role=False)