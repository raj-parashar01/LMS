import os
from pymongo import MongoClient

_client = None

def get_db():
    global _client
    if _client is None:
        mongo_uri = os.environ.get("MONGO_URI")
        if not mongo_uri:
            raise RuntimeError("MONGO_URI must be set; refusing to connect to a local MongoDB instance.")
        _client = MongoClient(mongo_uri)
    return _client["lms_db"]