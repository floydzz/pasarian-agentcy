"""Exercise queue uniqueness and worker claims on the real disposable MySQL DB."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker
from app.jobs import submit
from app.models import Campaign, Job, User
from app.workspace import Principal, principal

pytestmark = pytest.mark.real_auth


@pytest.fixture
def queue_db(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        user = User(email=f'{uuid4()}@queue.test', name='Queue test', password_hash='unused-test-account')
        first, second = Campaign(name='First queue resource', brief='test'), Campaign(name='Second queue resource', brief='test')
        db.add_all([user, first, second]); db.commit()
    yield factory, user.id, [first.id, second.id]
    with factory() as db:
        db.execute(delete(Job).where(Job.user_id == user.id))
        db.execute(delete(Campaign).where(Campaign.id.in_([first.id, second.id])))
        db.execute(delete(User).where(User.id == user.id)); db.commit()


def test_simultaneous_submissions_return_one_durable_job(queue_db):
    factory, user_id, campaigns = queue_db
    gate = Barrier(2)
    def enqueue(_):
        token = principal.set(Principal(user_id, 1, 'owner'))
        try:
            with factory(info={'workspace_id': 1}) as db:
                gate.wait(timeout=10)
                return submit(db, f'/campaigns/{campaigns[0]}/plan/stream', None, 'concurrent-key-' + str(campaigns[0])).id
        finally:
            principal.reset(token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(enqueue, range(2)))
    assert identities[0] == identities[1]
    with factory() as db:
        assert len(list(db.scalars(select(Job).where(Job.user_id == user_id)))) == 1


def test_two_workers_claim_distinct_jobs(queue_db, monkeypatch):
    from app import worker
    factory, user_id, campaigns = queue_db
    token = principal.set(Principal(user_id, 1, 'owner'))
    try:
        for identity in campaigns:
            with factory(info={'workspace_id': 1}) as db:
                submit(db, f'/campaigns/{identity}/plan/stream', None, f'claim-key-{identity}')
    finally:
        principal.reset(token)
    monkeypatch.setattr(worker, 'SessionLocal', factory)
    # Each worker process normally has its own heartbeat identity; prime the
    # shared test process once before the two claim threads start.
    with factory() as db:
        worker.touch_worker(db)
    gate = Barrier(2)
    def claim(_):
        gate.wait(timeout=10)
        return worker.claim().id
    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(claim, range(2)))
    assert len(set(identities)) == 2


def test_finalization_sees_checkpoints_despite_mysql_repeatable_read(queue_db):
    from types import SimpleNamespace
    from app.models import Concept, Variant, Asset
    from app.api.generation import _persist as persist_variants
    from app.api.assets import _persist as persist_assets
    factory, _, campaigns = queue_db
    with factory() as db:
        concept = Concept(campaign_id=campaigns[0], theme='Checkpoint', format='image', trend_rationale='', brand_rationale='', variant_count=1, variation_axes=['one'])
        db.add(concept); db.commit(); concept_id = concept.id
    with factory() as parent:
        assert list(parent.scalars(select(Variant).where(Variant.concept_id == concept_id))) == []
        with factory() as checkpoint:
            row = Variant(concept_id=concept_id, hook_type='one', headline='Saved', body='Saved', cta='Read more', visual_brief={})
            checkpoint.add(row); checkpoint.commit(); variant_id = row.id
        # The current-read lock must see the checkpoint, rather than attempt
        # to dereference/recreate a result absent from the old snapshot.
        assert persist_variants(parent, [(concept_id, None)])[0].id == variant_id
        parent.commit()
    with factory() as parent:
        assert list(parent.scalars(select(Asset).where(Asset.variant_id == variant_id))) == []
        with factory() as checkpoint:
            row = Asset(variant_id=variant_id, media_url='/media/checkpoint.png')
            checkpoint.add(row); checkpoint.commit(); asset_id = row.id
        output = SimpleNamespace(variant_id=variant_id, media_url='/media/duplicate.png', qa_status='passed', qa_notes=None)
        assert persist_assets(parent, [output])[0].id == asset_id
        parent.commit()
