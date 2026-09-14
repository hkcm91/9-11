# Application Surfaces

## `web-explorer/`

Planned public-facing map + timeline application.

Responsibilities:

- timeline scrubber
- map layers
- media markers and camera direction
- search/filtering
- nearby synchronized media
- story threads
- provenance/confidence display
- sensitive-content controls

The Explorer should consume verified/read-model data. It should not contain ingestion or historical-research logic.

## `workbench/`

Planned researcher/reviewer application.

Responsibilities:

- source registry
- ingestion status
- duplicate review
- time/location review queues
- entity resolution
- contradiction review
- evidence inspection
- revision history
- information-gain prioritization

The Workbench is where machine proposals become reviewed historical claims.

## `api/`

Planned API/read-model service shared by both applications.

Initial endpoints should eventually include:

- `GET /timeline?start=&end=`
- `GET /map?time=&bounds=`
- `GET /media/{id}`
- `GET /events/{id}`
- `GET /entities/{id}`
- `GET /story-threads/{id}`
- `GET /sources/{id}`

Write/review endpoints belong to the Workbench API and should require authentication.
