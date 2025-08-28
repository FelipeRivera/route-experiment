# Route Engine Experiment (Flask + A* + Redis + Postgres + Prometheus + Grafana + Nginx)

This project spins up a **local, Docker Compose** environment to stress-test a routing microservice.
The route engine uses **A\*** (with a time budget) over a graph built from **OpenStreetMap** data,
stores maps in **PostgreSQL**, caches frequent results in **Redis**, and exposes **Prometheus** metrics
that you can visualize in **Grafana**.

## Architecture

- **route_engine_a / route_engine_b**: Flask + Gunicorn microservices implementing A\*. Metrics at `/metrics`.
- **nginx**: load balancer in front of the route engines (HTTP on `:8080`).
- **postgres**: relational DB holding nodes/edges for each city.
- **redis**: cache for route results.
- **prometheus**: scrapes the engines' metrics.
- **grafana**: a pre-provisioned Prometheus datasource + a basic dashboard.
- **ingest_bogota**: one-shot loader that downloads Bogotá (drive) network and populates Postgres.

## Quickstart

1) **Start everything** (first time will run the Bogotá ingestion job automatically):

```bash
docker compose up -d --build
# wait ~1-3 minutes for the ingest job to finish
docker logs -f re_ingest_bogota
```

2) **Call the API** (through Nginx load balancer):

```bash
curl -s http://localhost:8080/route -H 'Content-Type: application/json' -d '{
  "city":"bogota",
  "source":{"lat":4.65,"lon":-74.05},
  "target":{"lat":4.70,"lon":-74.08},
  "constraints":{"cold_chain":true, "high_value":true, "security_conditions":true},
  "deadline_ms": 3000
}' | jq .
```

3) **Dashboards**:

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (user: admin / pass: admin)
  - Dashboard: **Route Experiment** ➜ includes request rate, duration P95, and A* expanded nodes.

## What the flags do

- `cold_chain` → penalizes roads that increase *temperature risk* (e.g., very slow/residential roads).
- `high_value` → penalizes roads with higher *security risk* (e.g., non-lit minor roads).
- `security_conditions` → additional security penalty similar to `high_value` (slightly lower weight).

The cost function is:

```
cost = travel_time * (1 + cold_chain*temp_risk + high_value*security_risk + 0.8*security_conditions*security_risk)
```

`travel_time` and risk scores are computed from OSM tags during ingestion.

## Degradation policy & the 3s budget

We run a bounded-time A*; if we run out of the `deadline_ms` (default 3000 ms):
- Return the best partial path found so far (`degraded=true, reason="timeout"`), or
- Fall back to the fastest path by base `travel_time` if no partial path is reconstructable.

This avoids hard failures while respecting the SLA goal.

## Load Testing

Example using **hey** (install locally) with a JSON payload file `req.json`:

```json
{
  "city":"bogota",
  "source":{"lat":4.65,"lon":-74.05},
  "target":{"lat":4.70,"lon":-74.08},
  "constraints":{"cold_chain":false, "high_value":true, "security_conditions":true},
  "deadline_ms": 3000
}
```

Run:

```bash
hey -z 2m -c 100 -m POST -T 'application/json' -d @req.json http://localhost:8080/route
```

## Importing other cities / custom areas

- Update the env vars of the `ingest_bogota` service in `docker-compose.yml`:
  - `CITY=medellin`, `PLACE_NAME=Medellín, Colombia`, etc.
- Or add an additional ingest service per city. The route engine loads any city by name.
