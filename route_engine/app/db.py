import psycopg2
import psycopg2.extras
import networkx as nx
import numpy as np

class DB:
    def __init__(self, host, port, dbname, user, password):
        self.conn = psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        self.conn.autocommit = True

    def ensure_city(self, city: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM cities WHERE name=%s", (city,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"City '{city}' not found. Run the ingest job.")
            return row[0]

    def load_graph(self, city: str):
        city_id = self.ensure_city(city)
        G = nx.DiGraph(city=city)

        # NODES (chunked)
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT osmid, x, y FROM nodes WHERE city_id=%s", (city_id,))
            while True:
                rows = cur.fetchmany(10000)
                if not rows:
                    break
                for r in rows:
                    osmid = int(r["osmid"])
                    G.add_node(osmid, x=float(r["x"]), y=float(r["y"]))

        # EDGES (chunked)
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT u, v, length, travel_time, highway, lit, temp_risk, security_risk "
                "FROM edges WHERE city_id=%s",
                (city_id,),
            )
            while True:
                rows = cur.fetchmany(10000)
                if not rows:
                    break
                for r in rows:
                    G.add_edge(
                        int(r["u"]),
                        int(r["v"]),
                        length=float(r["length"]),
                        travel_time=float(r["travel_time"]),
                        highway=r["highway"],
                        lit=bool(r["lit"]),
                        temp_risk=float(r["temp_risk"]),
                        security_risk=float(r["security_risk"]),
                    )

        # Build arrays for nearest-node queries
        nodes = list(G.nodes(data=True))
        idx_to_node = np.array([n for n, _ in nodes], dtype=np.int64)
        coords = np.array([[d["y"], d["x"]] for _, d in nodes], dtype=np.float64)  # lat, lon
        return G, idx_to_node, coords
