from fastapi import APIRouter

from app.api import auth, business, content, contracts, daily_rent, funnel1, funnel2, nda, offers, people, sign_docs, site, tax

api_router = APIRouter()
for r in (auth.router, people.router, funnel1.router, funnel2.router, business.router, contracts.router, contracts.public, content.router, content.public, nda.router, nda.public, sign_docs.router, sign_docs.public, daily_rent.router, daily_rent.public, offers.router, site.public, tax.router):
    api_router.include_router(r)
