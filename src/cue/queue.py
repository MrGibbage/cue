from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.models import Job, JobAttempt


def claim_next_job(session: Session, worker_id: str) -> Job | None:
    """Claim one queued job inside the caller's transaction."""
    job = session.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1))
    if job is None:
        return None
    job.status = "running"
    job.claimed_by = worker_id
    job.claimed_at = datetime.now(UTC).replace(tzinfo=None)
    job.attempt_count += 1
    session.add(JobAttempt(job_id=job.id, attempt_number=job.attempt_count, status="running"))
    session.flush()
    return job


def finish_job(session: Session, job: Job, *, error: str | None = None) -> None:
    attempt = session.scalars(
        select(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.attempt_number == job.attempt_count)
    ).one()
    attempt.finished_at = datetime.now(UTC).replace(tzinfo=None)
    attempt.error = error
    attempt.status = "succeeded" if error is None else "failed"
    job.claimed_by = None
    job.claimed_at = None
    job.last_error = error
    if error is None:
        job.status = "succeeded"
    elif job.attempt_count >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "queued"
