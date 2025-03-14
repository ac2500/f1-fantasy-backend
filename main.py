from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root route to check if backend is running
@app.get("/")
def read_root():
    return {"message": "F1 Fantasy Backend is Running!"}

# ✅ Add this endpoint to send team data to the frontend
@app.get("/teams")
def get_teams():
    return {
        "teams": [
            {"name": "Red Bull Racing", "drivers": ["Max Verstappen", "Sergio Perez"], "points": 0},
            {"name": "Mercedes", "drivers": ["Lewis Hamilton", "George Russell"], "points": 0},
            {"name": "Ferrari", "drivers": ["Charles Leclerc", "Carlos Sainz"], "points": 0},
            {"name": "McLaren", "drivers": ["Lando Norris", "Oscar Piastri"], "points": 0},
            {"name": "Aston Martin", "drivers": ["Fernando Alonso", "Lance Stroll"], "points": 0}
        ]
    }