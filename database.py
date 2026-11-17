import os
from pymongo import MongoClient

_client = None

def get_db():
    global _client
    if _client is None:
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
        _client = MongoClient(mongo_uri)
    return _client["lms_db"]