from locust import HttpUser, task, between
import os, random, json, math, time

# ---------------------------
# Config
# ---------------------------
# Usa rutas RELATIVAS. El host base lo define la UI o el flag -H (p.ej., http://nginx dentro de Docker).
CITY = os.getenv("CITY", "bogota")
DEADLINE_MS = int(os.getenv("DEADLINE_MS", "3000"))

# BBOX de Bogotá aprox (lat_min, lat_max, lon_min, lon_max)
BBOX_ENV = os.getenv("CITY_BBOX", "")
if BBOX_ENV:
    lat_min, lat_max, lon_min, lon_max = [float(x) for x in BBOX_ENV.split(",")]
else:
    lat_min, lat_max = 4.47, 4.83
    lon_min, lon_max = -74.21, -73.99

# Hotspots urbanos (aprox). Ayudan a que haya vías cercanas y rutas válidas:
HOTSPOTS = [
    (4.653, -74.062),  # Chapinero
    (4.711, -74.030),  # Usaquén
    (4.609, -74.081),  # Centro
    (4.703, -74.130),  # Engativá
    (4.631, -74.157),  # Kennedy
    (4.748, -74.083),  # Suba
]

# Pool grande de rutas pre-generadas (se reparte entre VUs para buen cache hit)
POOL_SIZE = int(os.getenv("ROUTE_POOL_SIZE", "300"))

# ---------------------------
# Utilidades geográficas
# ---------------------------
def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))

def jitter_km(lat, lon, km):
    """Desplaza un punto aleatoriamente hasta 'km' kilómetros."""
    # 1° lat ~ 111 km; 1° lon ~ 111 km * cos(lat)
    dlat = (random.uniform(-km, km)) / 111.0
    dlon = (random.uniform(-km, km)) / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (lat + dlat, lon + dlon)

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi/2)**2
         + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2)
    return 2*R*math.asin(math.sqrt(a))

def random_point_in_bbox():
    lat = random.uniform(lat_min, lat_max)
    lon = random.uniform(lon_min, lon_max)
    return (lat, lon)

def random_point_near_hotspot(max_km=1.5):
    base = random.choice(HOTSPOTS)
    lat, lon = jitter_km(base[0], base[1], max_km)
    return (clamp(lat, lat_min, lat_max), clamp(lon, lon_min, lon_max))

def random_constraints():
    # Probabilidades: ajusta a gusto
    cold = random.random() < 0.35
    high = random.random() < 0.35
    sec  = random.random() < 0.35
    # A veces fuerza al menos una bandera para ver impacto
    if not (cold or high or sec) and random.random() < 0.4:
        choice = random.choice(["cold", "high", "sec"])
        if choice == "cold": cold = True
        elif choice == "high": high = True
        else: sec = True
    return {"cold_chain": cold, "high_value": high, "security_conditions": sec}

def gen_route_pair():
    """Genera un par (source, target) con mezcla de distancias:
       - 30% intra-zona (~0.5–3 km)
       - 50% ciudad (~3–12 km)
       - 20% largo (~12–25 km)
    """
    r = random.random()
    # 60–80% cerca de hotspots para rutas más confiables
    use_hotspots = r < 0.8

    # Objetivos de distancia
    if r < 0.30:
        dmin, dmax = 0.5, 3     # intra-zona
    elif r < 0.80:
        dmin, dmax = 3, 12      # ciudad
    else:
        dmin, dmax = 12, 25     # largo

    for _ in range(20):
        s = random_point_near_hotspot(1.5) if use_hotspots else random_point_in_bbox()
        # Para trayecto corto, destino cerca del mismo hotspot
        if dmax <= 3:
            t = jitter_km(s[0], s[1], 2.5)  # a <=2.5km
        else:
            t = random_point_near_hotspot(2.5) if use_hotspots else random_point_in_bbox()

        s = (clamp(s[0], lat_min, lat_max), clamp(s[1], lon_min, lon_max))
        t = (clamp(t[0], lat_min, lat_max), clamp(t[1], lon_min, lon_max))
        d = haversine_km(s[0], s[1], t[0], t[1])
        if dmin <= d <= dmax:
            return s, t
    # fallback: puntos al azar si no salió nada
    return random_point_in_bbox(), random_point_in_bbox()

# ---------------------------
# Construir un pool grande
# ---------------------------
ROUTE_POOL = []
def build_route_pool(n=POOL_SIZE):
    seen = set()
    while len(ROUTE_POOL) < n:
        s, t = gen_route_pair()
        key = (round(s[0], 5), round(s[1], 5), round(t[0], 5), round(t[1], 5))
        if key in seen:
            continue
        seen.add(key)
        ROUTE_POOL.append({"s": {"lat": s[0], "lon": s[1]},
                           "t": {"lat": t[0], "lon": t[1]},
                           "flags": random_constraints()})

build_route_pool()

# ---------------------------
# Usuario de carga
# ---------------------------
class RouteUser(HttpUser):
    wait_time = between(0.05, 0.4)

    def on_start(self):
        # Random seed por usuario para diversificar
        random.seed(time.time() + os.getpid() + id(self))
        # Warm-up: calienta cache con algunas rutas del pool
        for _ in range(5):
            self._post_random_route(DEADLINE_MS)

    @task(6)
    def post_route_normal(self):
        self._post_random_route(DEADLINE_MS)

    @task(2)
    def post_route_strict(self):
        # más estricto para inducir degradación ocasional
        strict = max(1500, DEADLINE_MS // 2)
        self._post_random_route(strict)

    @task(1)
    def post_route_long(self):
        # fuerza una ruta larga (reusa pool, pero con deadline estándar)
        self._post_random_route(DEADLINE_MS, prefer_long=True)

    def _pick_from_pool(self, prefer_long=False):
        # Si prefer_long, sesga a rutas con distancia>10km (a ojo)
        if prefer_long:
            # sample algunos y elige el más largo aprox por bbox (heurística simple)
            candidates = random.sample(ROUTE_POOL, k=min(15, len(ROUTE_POOL)))
            def rough_dist_km(a, b):
                return haversine_km(a["s"]["lat"], a["s"]["lon"], a["t"]["lat"], a["t"]["lon"])
            return max(candidates, key=lambda r: rough_dist_km(r, None))
        return random.choice(ROUTE_POOL)

    def _post_random_route(self, deadline_ms, prefer_long=False):
        r = self._pick_from_pool(prefer_long=prefer_long)
        payload = {
            "city": CITY,
            "source": {"lat": r["s"]["lat"], "lon": r["s"]["lon"]},
            "target": {"lat": r["t"]["lat"], "lon": r["t"]["lon"]},
            "constraints": r["flags"],
            "deadline_ms": deadline_ms
        }
        # NOTA: usamos ruta relativa; el host/puerto vienen de -H o UI de Locust
        with self.client.post(
            "/route",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            name="/route",
            catch_response=True
        ) as res:
            if res.status_code != 200:
                res.failure(f"HTTP {res.status_code}")
                return
            try:
                j = res.json()
            except Exception as e:
                res.failure(f"JSON parse error: {e}")
                return
            if not isinstance(j.get("geometry"), list) or len(j["geometry"]) < 2:
                # puede ocurrir con OD realmente raros; el servicio intenta fallback/degradado
                res.failure("geometry ausente o muy corta")
                return
            res.success()
