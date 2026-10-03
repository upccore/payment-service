from fastapi import FastAPI

from app.api import router

app = FastAPI(title="Payment Service")
app.include_router(router)
