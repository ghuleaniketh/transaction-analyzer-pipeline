import redis
from rq import Queue
from app.config import settings

redis_conn = redis.from_url(settings.REDIS_URL)

queue = Queue(
    "default",
    connection=redis_conn
)