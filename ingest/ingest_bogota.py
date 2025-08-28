import os
import time
import psycopg2
import osmnx as ox
import networkx as nx

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "routes")
DB_USER = os.getenv("DB_USER", "routeuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "routepass")
CITY = (os.getenv("CITY", "bogota")).lower()
PLACE_NAME = os.getenv("PLACE_NAME", "Bogotá, Colombia")

def risk_from_tags(highway:str, lit:bool):
    # simple, deterministic scoring for demo purposes
    hw = (highway or "").lower()
    # temperature risk: prefer faster roads for cold chain
    temp_map = {
        "motorway": 0.0, "trunk": 0.1, "primary": 0.2, "secondary": 0.35, "tertiary": 0.5,
        "unclassified": 0.6, "residential": 0.7, "service": 0.8, "track": 0.9
    }
    temp_risk = temp_map.get(hw, 0.5)
    # security risk: prefer well-lit major roads
    security_risk = 0.1 if (hw in ["motorway","trunk","primary"] and lit) else 0.3 if hw in ["secondary","tertiary"] else 0.7
    return temp_risk, security_risk

def main():
    print(f"[ingest] downloading street network for {PLACE_NAME} ...", flush=True)
    G = ox.graph_from_place(PLACE_NAME, network_type="drive", simplify=True)
    G = ox.add_edge_speeds(G)         # km/h
    G = ox.add_edge_travel_times(G)   # seconds

    print("[ingest] connecting to Postgres ...", flush=True)
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("INSERT INTO cities(name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (CITY,))
        cur.execute("SELECT id FROM cities WHERE name=%s", (CITY,))
        city_id = cur.fetchone()[0]

    # insert nodes
    print("[ingest] inserting nodes ...", flush=True)
    with conn.cursor() as cur:
        args = []
        for n, d in G.nodes(data=True):
            args.append((city_id, int(n), float(d["x"]), float(d["y"])))
            if len(args) >= 5000:
                psycopg2.extras.execute_values(cur, "INSERT INTO nodes(city_id, osmid, x, y) VALUES %s ON CONFLICT DO NOTHING", args)
                args.clear()
        if args:
            psycopg2.extras.execute_values(cur, "INSERT INTO nodes(city_id, osmid, x, y) VALUES %s ON CONFLICT DO NOTHING", args)

    # insert edges
    print("[ingest] inserting edges ...", flush=True)
    with conn.cursor() as cur:
        args = []
        for u, v, k, d in G.edges(keys=True, data=True):
            hw = d.get("highway")
            if isinstance(hw, list): hw = hw[0]
            lit = str(d.get("lit", "no")).lower() in ("1","true","yes")
            temp_risk, security_risk = risk_from_tags(hw, lit)
            length = float(d.get("length", 1.0))
            tt = float(d.get("travel_time", length/8.0))
            args.append((city_id, int(u), int(v), length, tt, hw or "", lit, temp_risk, security_risk))
            if len(args) >= 5000:
                psycopg2.extras.execute_values(cur, 
                    "INSERT INTO edges(city_id, u, v, length, travel_time, highway, lit, temp_risk, security_risk) VALUES %s ON CONFLICT DO NOTHING", 
                    args)
                args.clear()
        if args:
            psycopg2.extras.execute_values(cur, 
                "INSERT INTO edges(city_id, u, v, length, travel_time, highway, lit, temp_risk, security_risk) VALUES %s ON CONFLICT DO NOTHING", 
                args)

    print("[ingest] done.", flush=True)

if __name__ == "__main__":
    import psycopg2.extras
    main()
