import os

class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "routes")
    DB_USER = os.getenv("DB_USER", "routeuser")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "routepass")

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

    DEFAULT_CITY = os.getenv("DEFAULT_CITY", "bogota")
    ROUTE_DEADLINE_MS = int(os.getenv("ROUTE_DEADLINE_MS", "3000"))
