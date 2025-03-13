from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "F1 Fantasy Backend is Running!"}
