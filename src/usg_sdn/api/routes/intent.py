"""Intent CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.intent import IntentDocument
from ...store import IntentRepo, get_session

router = APIRouter()


@router.get("", response_model=IntentDocument)
async def get_intent(session: AsyncSession = Depends(get_session)) -> IntentDocument:
    doc = await IntentRepo(session).load()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no intent stored")
    return doc


@router.put("", response_model=IntentDocument)
async def put_intent(
    doc: IntentDocument,
    session: AsyncSession = Depends(get_session),
) -> IntentDocument:
    await IntentRepo(session).save(doc)
    return doc
