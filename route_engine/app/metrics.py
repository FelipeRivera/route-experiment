from prometheus_client import Counter, Histogram

REQUESTS = Counter("route_requests_total", "Total route requests", ["city", "degraded", "cache_hit"])
FAILURES = Counter("route_failures_total", "Route calculation failures", ["city", "reason"])
DURATION = Histogram("route_duration_seconds", "Route calculation duration (seconds)", buckets=[0.05,0.1,0.2,0.5,1,1.5,2,2.5,3,4,5,10])
EXPANDED = Histogram("astar_expanded_nodes", "Number of nodes expanded by A*", buckets=[10,50,100,200,400,800,1600,3200,6400])
