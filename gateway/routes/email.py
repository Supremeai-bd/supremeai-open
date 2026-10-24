from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security.authentication.rbac import get_current_user_token
from tools.social.email_agent import EmailAgent

router = APIRouter(
    prefix="/integrations/email", tags=["email"], dependencies=[Depends(get_current_user_token)]
)
email_agent = EmailAgent()


class GmailAuthRequest(BaseModel):
    provider: str
    scopes: list[str]


class ImapAuthRequest(BaseModel):
    host: str
    port: int
    username: str
    app_password: str


@router.post("/gmail")
async def gmail_auth(payload: GmailAuthRequest):
    try:
        success = email_agent.connect_gmail_oauth(payload.provider, payload.scopes)
        if success:
            return {"status": "success", "message": "Connected Gmail via OAuth"}
        raise HTTPException(status_code=400, detail="Failed to connect Gmail OAuth")
    except NotImplementedError as e:
        # গ্যাপ ফিক্স: আগে এই পাথে কখনো পৌঁছানো যেত না কারণ connect_gmail_oauth() সবসময় True
        # রিটার্ন করত (fake success)। এখন real না-হওয়া অবস্থা 501 হিসেবে honestly রিপোর্ট হয়।
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/imap")
async def imap_auth(payload: ImapAuthRequest):
    try:
        success = email_agent.connect_imap(
            payload.host, payload.port, payload.username, payload.app_password
        )
        if success:
            return {"status": "success", "message": "Connected generic IMAP"}
        raise HTTPException(status_code=400, detail="Failed to connect generic IMAP")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
