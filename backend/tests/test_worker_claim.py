"""11-20..11-22 the job queue stood: post_viewing_survey on a lead with nothing to do rolled its claim back
(leads.mark_viewing_done → db.rollback) and came first in every pass. A handler that rolls back still ends its job."""
from datetime import timedelta

from app import worker
from app.models import Job
from app.services import jobs
from app.services.common import now


def test_a_handler_that_rolls_back_still_ends_its_job(db, monkeypatch):
    def rolls_back(s, job):
        s.rollback()
        return "stale"
    monkeypatch.setitem(worker.HANDLERS, "test_rollback", rolls_back)
    jobs.schedule(db, "test_rollback", 1, now() - timedelta(minutes=1))
    jobs.schedule(db, "test_rollback", 2, now())
    db.commit()
    assert worker.tick(limit=5) == {"stale": 2}
    db.expire_all()
    assert all(j.done_at is not None and j.attempts == 1 for j in db.query(Job).filter_by(kind="test_rollback"))
