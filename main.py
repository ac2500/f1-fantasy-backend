// main.js (excerpt with requested changes)

// Existing global declarations
let tradeHistory = [];
let processedRaces = [];

// ...

async function loadSeasonData(seasonId) {
  fetch(`${backendUrl}/get_season?season_id=${encodeURIComponent(seasonId)}`)
    .then(res => res.json())
    .then(data => {
      processedRaces = data.processed_races || [];
      // existing code follows...
    });
}

// 10) Refresh Race Points (next unprocessed round)
async function refreshRacePoints() {
  if (!currentSeasonId) {
    return alert("No season_id in context!");
  }

  // Determine next race number: highest processed + 1, or start at 4
  const nextRace = processedRaces.length > 0
    ? Math.max(...processedRaces.map(r => parseInt(r, 10))) + 1
    : 4;

  try {
    const res = await fetch(
      `${backendUrl}/update_race_points?` +
      `season_id=${encodeURIComponent(currentSeasonId)}` +
      `&race_id=${encodeURIComponent(nextRace)}`,
      { method: "POST" }
    );
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || json.error);
    alert(json.message);
    // Reload season data (processedRaces will update)
    await loadSeasonData(currentSeasonId);
  } catch (err) {
    if (err.message.includes("already been processed") || err.message.includes("No new races")) {
      alert("No new races to update points.");
    } else {
      alert(err.message || err);
    }
  }
}