"""Use independent real transactions to exercise the campaign conversion lock."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.marketing_calendar import campaign_for_item
from app.models import Campaign, Conversation, MarketingPlan, MarketingPlanItem


def test_two_simultaneous_requests_create_one_campaign(engine):
    with Session(engine) as db:
        plan=MarketingPlan(name='Concurrent conversion test',start_date=date(2027,1,1),end_date=date(2027,12,31))
        db.add(plan);db.flush()
        item=MarketingPlanItem(plan_id=plan.id,title='Concurrent test item',strategy='Use approved brand claims',campaign_start=date(2027,8,1),campaign_end=date(2027,8,31),preparation_start=date(2027,7,1),status='planned',source_snapshot={})
        db.add(item);db.commit();item_id,plan_id=item.id,plan.id
    barrier=Barrier(2)
    def convert():
        with Session(engine,expire_on_commit=False) as db:
            barrier.wait(timeout=5)
            return campaign_for_item(db,item_id,1)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:convert(),range(2)))
        assert results[0]['campaign_id']==results[1]['campaign_id']
        assert results[0]['conversation_id']==results[1]['conversation_id']
        with Session(engine) as db:
            assert len(list(db.scalars(select(Campaign).where(Campaign.name=='Concurrent test item'))))==1
    finally:
        with Session(engine) as db:
            item=db.get(MarketingPlanItem,item_id)
            if item and item.campaign_id:
                cid=item.campaign_id
                db.execute(delete(Conversation).where(Conversation.campaign_id==cid))
                db.delete(item);db.flush()
                db.execute(delete(Campaign).where(Campaign.id==cid))
            elif item:db.delete(item)
            db.execute(delete(MarketingPlan).where(MarketingPlan.id==plan_id));db.commit()
