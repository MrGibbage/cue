from cue.models import Job, User
from cue.queue import claim_next_job, finish_job


def test_job_claim_and_retry_state(session):
    user = User(username="owner", password_hash="hash")
    session.add(user)
    session.flush()
    job = Job(owner_id=user.id, kind="resolve_source_snapshot")
    session.add(job)
    session.commit()

    claimed = claim_next_job(session, "test-worker")
    assert claimed is not None
    assert claimed.status == "running"
    finish_job(session, claimed, error="temporary problem")
    assert claimed.status == "queued"
    assert claimed.attempt_count == 1
    session.commit()


def test_job_fails_after_its_bounded_attempts(session):
    user = User(username="owner", password_hash="hash")
    session.add(user)
    session.flush()
    job = Job(owner_id=user.id, kind="resolve_source_snapshot", max_attempts=2)
    session.add(job)
    session.commit()

    for _ in range(2):
        claimed = claim_next_job(session, "test-worker")
        assert claimed is not None
        finish_job(session, claimed, error="temporary problem")
        session.commit()

    assert job.status == "failed"
