from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.authentication import login
from app.batches import allbatches

app= FastAPI(title="Assignment agents")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/test")
async def health():
    return {"status":"ok"}


app.include_router(login.LoginRouter)
app.include_router(allbatches.Batchesrouter)