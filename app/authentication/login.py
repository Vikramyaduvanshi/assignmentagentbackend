
import logging
import os

import requests
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException,Response,Depends
from pycognito.aws_srp import AWSSRP
from pydantic import BaseModel
from typing import Annotated
# from app.authentication.refreshToken import _resolve
from app.authentication.refreshToken import get_erp_headers_no_role

log = logging.getLogger("auth")

# ---------------- config (env se, hard-code nahi) ----------------
POOL_ID = os.getenv("pool_id")
CLIENT_ID = os.getenv("client_id")
REGION = os.getenv("pool_region")                      
COGNITO_URL = f"https://cognito-idp.{REGION}.amazonaws.com/"
ERP_BASE = os.getenv("ERP_BASE")
# -----------------------------------------------------------------

LoginRouter = APIRouter(prefix="/auth8178", tags=["auth"])


class User(BaseModel):
    email: str
    password: str


# class RefreshBody(BaseModel):
#     refresh_token: str


def _fetch_roles(access_token: str):
    """userprofile se roles. Fail ho to login fail nahi hona chahiye, khaali list do."""
    try:
        r = requests.get(
            f"{ERP_BASE}/us/users/userprofile",
            headers={"Authorization": access_token},
            timeout=15,
        )
        if not r.ok:
            return []
        roles = r.json()["data"].get("user_roles", [])
        return [{"user_role_id": x["id"], "role_id": x["role_id"], "zone_id": x["zone_id"],"branch_code": x["zone"]["code"], "branch_name": x["zone"]["name"]} for x in roles]
    except Exception as e:
        log.warning("userprofile fetch fail: %s", type(e).__name__)
        return []


@LoginRouter.post("/login")
async def login_user(user: User,response:Response):
    # sync `def` rakha hai: pycognito/requests blocking hain, FastAPI isse threadpool me chalata hai
    email = user.email.strip().lower()
    print(user)
    if not email or not user.password:
        raise HTTPException(status_code=400, detail="Email aur password dono chahiye")

    try:
        srp = AWSSRP(
            username=email,
            password=user.password,
            pool_id=POOL_ID,
            client_id=CLIENT_ID,
            pool_region=REGION,
        )
        result = srp.authenticate_user()["AuthenticationResult"]

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            # dono ke liye same message, taaki pata na chale ki email exist karta hai ya nahi
            raise HTTPException(status_code=401, detail="Email ya password galat hai")
        if code in ("UserNotConfirmedException", "PasswordResetRequiredException"):
            raise HTTPException(status_code=403, detail="Account login ke liye ready nahi hai, admin se baat karo")
        if code == "TooManyRequestsException" or code == "LimitExceededException":
            raise HTTPException(status_code=429, detail="Bahut zyada koshish, thodi der baad try karo")
        log.error("cognito error: %s", code)
        raise HTTPException(status_code=502, detail="Login service abhi available nahi hai")

    except Exception as e:
        # password kabhi log me nahi jata, sirf exception ka type
        log.error("login unexpected error: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Login me kuch gadbad hui")
    response.set_cookie(
        key="access_token",
        value=result["AccessToken"],
        httponly=True,
        secure=False,
        samesite="lax",
        max_age= 60 * 60
        )
    
    response.set_cookie(
        key="refresh_token",
        value=result.get("RefreshToken"),
        httponly=True,
        secure=False,
        samesite="lax",
        max_age= 30 * 24 * 60 * 60
        )
    

    return {"message":"login successfully", "success":True}



# @LoginRouter.post("/refresh")
# def refresh_token(body: RefreshBody):
#     try:
#         r = requests.post(
#             COGNITO_URL,
#             headers={
#                 "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
#                 "Content-Type": "application/x-amz-json-1.1",
#             },
#             json={
#                 "AuthFlow": "REFRESH_TOKEN_AUTH",
#                 "ClientId":  CLIENT_ID,
#                 "AuthParameters": {"REFRESH_TOKEN": body.refresh_token},
#             },
#             timeout=15,
#         )
#     except requests.RequestException as e:
#         log.error("refresh network error: %s", type(e).__name__)
#         raise HTTPException(status_code=502, detail="Login service abhi available nahi hai")

#     if r.status_code == 400:
#         raise HTTPException(status_code=401, detail="Refresh token invalid ya expire hai, dobara login karo")
#     if not r.ok:
#         raise HTTPException(status_code=502, detail="Token refresh nahi ho paya")

#     res = r.json()["AuthenticationResult"]
#     return {
#         "access_token": res["AccessToken"],
#         "expires_in": res.get("ExpiresIn", 3600),
#         "token_type": "access",
#     }


headres = Annotated[dict, Depends(get_erp_headers_no_role)]

@LoginRouter.post("/profile")
async def profile(header:headres):
    print(header)
    result= _fetch_roles(header["access_token"])
    return {"result":result, "success":True}


