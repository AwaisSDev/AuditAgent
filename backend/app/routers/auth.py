"""Email+password signup, bypassing Supabase's email-confirmation step.

This exists only because confirming an email requires either clicking a
real email link (slow for local dev/demo) or using the admin API's
`email_confirm=True`, which only the service-role key can set — the
dashboard's anon/publishable key can't do this via a plain `signUp()` call.
Sign-in itself still goes straight from the dashboard to Supabase Auth
(app/login/page.tsx) — this endpoint only covers account creation.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: str  # Supabase itself validates email format and rejects malformed ones
    password: str


@router.post("/signup", status_code=201)
async def signup(body: SignupIn) -> dict:
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    db = get_db()
    try:
        result = db.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                "email_confirm": True,  # skip the confirmation-link step entirely
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"user_id": result.user.id}
