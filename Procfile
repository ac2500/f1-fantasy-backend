from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global variables
registered_teams = {}
draft_ready = set()

@app.get("/register_team")
def register_team(team_name: str):
    global registered_teams
    if team_name in registered_teams:
        return {"error": "Team name already registered"}
    
    registered_teams[team_name] = "Waiting to enter draft mode..."
    return {"message": f"{team_name} registered successfully!", "status": registered_teams[team_name]}

@app.get("/enter_draft_mode")
def enter_draft_mode(team_name: str):
    global registered_teams, draft_ready
    if team_name not in registered_teams:
        return {"error": "Team not registered"}

    draft_ready.add(team_name)
    registered_teams[team_name] = "Waiting for draft to start..."

    # If all 3 players are ready, start the draft automatically
    if len(draft_ready) == 3:
        return start_draft()

    return {"message": f"{team_name} entered draft mode!", "status": registered_teams[team_name]}

@app.get("/get_registered_teams")
def get_registered_teams():
    global registered_teams
    return {"teams": registered_teams}

@app.get("/start_draft")
def start_draft():
    global draft_ready
    if len(draft_ready) < 3:
        return {"error": "Not enough players to start the draft!"}

    draft_order = list(draft_ready)
    draft_ready.clear()  # Clear draft_ready after starting the draft
    return {"message": "Draft started!", "draft_order": draft_order}
