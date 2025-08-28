from flask import Flask, request, jsonify
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app
import numpy as np
import networkx as nx

from .config import Config
from .db import DB
from .cache import Cache
from .metrics import REQUESTS, FAILURES, DURATION, EXPANDED
from .a_star import astar_with_deadline
from .utils import haversine

# Global singleton-ish (simple demo)
DB_CONN = None
CACHE = None
GRAPHS = {}  # city -> (G, idx_to_node, coords)


def load_city_if_needed(city, cfg):
    global GRAPHS, DB_CONN
    if city in GRAPHS:
        return GRAPHS[city]
    if DB_CONN is None:
        DB_CONN = DB(cfg.DB_HOST, cfg.DB_PORT, cfg.DB_NAME, cfg.DB_USER, cfg.DB_PASSWORD)
    G, idx_to_node, coords = DB_CONN.load_graph(city)
    GRAPHS[city] = (G, idx_to_node, coords)
    return GRAPHS[city]


def build_weight_func(constraints):
    cc = 1.0 if constraints.get("cold_chain") else 0.0
    hv = 1.0 if constraints.get("high_value") else 0.0
    sc = 1.0 if constraints.get("security_conditions") else 0.0

    # Penalty model: base on travel_time, add risk-sensitive multipliers
    def weight(data):
        tt = float(data.get("travel_time", data.get("length", 1.0) / 8.0))  # seconds
        temp_risk = float(data.get("temp_risk", 0.3))      # 0..1
        security_risk = float(data.get("security_risk", 0.3))  # 0..1
        penalty = (cc * temp_risk) + (hv * security_risk) + (sc * security_risk * 0.8)
        return tt * (1.0 + penalty)
    return weight


def create_app():
    app = Flask(__name__)
    cfg = Config()
    global CACHE
    CACHE = Cache(cfg.REDIS_HOST, cfg.REDIS_PORT, cfg.REDIS_DB)

    # attach /metrics
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})

    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    @app.post("/route")
    def route():
        payload = request.get_json(force=True)
        city = (payload.get("city") or cfg.DEFAULT_CITY).lower()
        src = payload["source"]
        dst = payload["target"]
        constraints = payload.get("constraints", {})
        deadline_ms = int(payload.get("deadline_ms", cfg.ROUTE_DEADLINE_MS))

        # cache lookup first
        cached = CACHE.get(city, src, dst, constraints)
        if cached:
            REQUESTS.labels(city=city, degraded=str(cached.get("degraded", False)), cache_hit="true").inc()
            return jsonify(cached), 200

        # ensure graph is loaded
        G, idx_to_node, coords = load_city_if_needed(city, cfg)

        try:
            src_lat = float(src.get("lat"))
            src_lon = float(src.get("lon"))
            dst_lat = float(dst.get("lat"))
            dst_lon = float(dst.get("lon"))
        except (TypeError, ValueError):
            return jsonify({"error": "bad_request", "detail": "source/target lat/lon must be numbers"}), 400

        # map lat/lon to nearest osmid
        src_arr = np.array([src_lat, src_lon], dtype=np.float64)
        dst_arr = np.array([dst_lat, dst_lon], dtype=np.float64)
        # rough nearest (euclidean in lat/lon) - OK for city scale
        s_idx = np.argmin(np.sum((coords - src_arr) ** 2, axis=1))
        t_idx = np.argmin(np.sum((coords - dst_arr) ** 2, axis=1))
        s = int(idx_to_node[s_idx]); t = int(idx_to_node[t_idx])

        # build heuristic using haversine -> optimistic travel time assuming 60 km/h
        def heuristic(node):
            ndata = G.nodes[node]
            dist_m = haversine(ndata["y"], ndata["x"], dst_arr[0], dst_arr[1])
            return dist_m / 16.6666667  # seconds at 60 km/h (≈16.67 m/s)

        weight_func = build_weight_func(constraints)

        # run
        deadline_sec = max(0.05, deadline_ms / 1000.0)
        with DURATION.time():
            path, cost, expanded, degraded, reason = astar_with_deadline(G, s, t, heuristic, weight_func, deadline_sec)
        EXPANDED.observe(expanded)

        if not path:
            # hard fallback: try fastest by base travel_time
            try:
                path = nx.shortest_path(G, s, t, weight="travel_time")
                degraded = True
                reason = "fallback_dijkstra"
                # estimate cost
                cost = sum(G.edges[u, v].get("travel_time", 1.0) for u, v in zip(path[:-1], path[1:]))
            except Exception as e:
                FAILURES.labels(city=city, reason=reason or "unreachable").inc()
                REQUESTS.labels(city=city, degraded="true", cache_hit="false").inc()
                return jsonify({"error": "no_path", "detail": str(e)}), 422

        # build coordinates
        coords_out = [{"lat": float(G.nodes[n]["y"]), "lon": float(G.nodes[n]["x"])} for n in path]
        resp = {
            "city": city,
            "source_node": s,
            "target_node": t,
            "constraints": constraints,
            "degraded": degraded,
            "reason": reason or "",
            "travel_time_sec_est": cost,
            "nodes": path,
            "geometry": coords_out,
            "expanded_nodes": expanded,
        }

        CACHE.set(city, src, dst, constraints, resp, ttl=3600)
        REQUESTS.labels(city=city, degraded=str(degraded), cache_hit="false").inc()
        return jsonify(resp), 200

    return app
