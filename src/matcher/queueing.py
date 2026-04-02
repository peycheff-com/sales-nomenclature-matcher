from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.repos.match import MatchRepo


async def enqueue_unique_job(arq_pool, job_name: str, job_id: str, queue_name: str, **kwargs):
    return await arq_pool.enqueue_job(
        job_name,
        job_id,
        _queue_name=queue_name,
        _job_id=job_id,
        **kwargs,
    )


async def enqueue_request_job(
    *,
    db: AsyncSession,
    arq_pool,
    request_id: str,
    job_name: str,
    queue_name: str,
    job_payload: dict | None = None,
) -> None:
    repo = MatchRepo(db)
    try:
        await enqueue_unique_job(
            arq_pool,
            job_name,
            request_id,
            queue_name,
            **(job_payload or {}),
        )
        await repo.update_request_status(request_id, "queued", error_message=None)
        await db.commit()
    except Exception as exc:
        await repo.update_request_status(
            request_id,
            "failed",
            error_message=f"enqueue_failed: {exc}",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue background job",
        ) from exc
