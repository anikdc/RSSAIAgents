import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_FILE = Path("briefing_data.json")
FEEDS_DB_FILE = Path("feeds_db.json")
TRUSTED_FEEDS_FILE = Path("feeds_default.json")
RUNTIME_DIR = Path(".runtime")
JOBS_FILE = RUNTIME_DIR / "jobs.json"
CACHE_FILE = RUNTIME_DIR / "pipeline_cache.json"


def _now():
    return datetime.now().isoformat()


def _read_json(path: Path, default: Any):
    if not path.exists():
        return deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return deepcopy(default)


def _write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class JsonPersistence:
    """Local fallback persistence that preserves the current file-based workflow."""

    kind = "json"

    def get_latest_briefing(self):
        return _read_json(DATA_FILE, None)

    def save_briefing(self, briefing):
        _write_json(DATA_FILE, briefing)
        return briefing

    def get_job(self, job_id):
        return _read_json(JOBS_FILE, {}).get(job_id)

    def upsert_job(self, job):
        jobs = _read_json(JOBS_FILE, {})
        job = {**job, "updated_at": _now()}
        jobs[job["id"]] = job
        _write_json(JOBS_FILE, jobs)
        return job

    def append_job_event(self, job_id, event):
        job = self.get_job(job_id) or {"id": job_id, "events": []}
        events = job.setdefault("events", [])
        events.append(event)
        job["phase"] = event.get("phase", job.get("phase"))
        return self.upsert_job(job)

    def list_feeds(self):
        feeds = _read_json(FEEDS_DB_FILE, [])
        trusted = set(_read_json(TRUSTED_FEEDS_FILE, []))
        for feed in feeds:
            feed["trusted"] = feed.get("url") in trusted
        return feeds

    def add_feed(self, feed):
        feeds = self.list_feeds()
        if any(existing.get("url") == feed["url"] for existing in feeds):
            raise ValueError("This feed URL already exists.")

        saved = {
            "url": feed["url"],
            "name": feed["name"],
            "categories": feed.get("categories", []),
            "region": feed.get("region", "global"),
        }
        feeds.append(saved)
        _write_json(FEEDS_DB_FILE, [{k: v for k, v in item.items() if k != "trusted"} for item in feeds])

        if feed.get("trusted"):
            trusted = _read_json(TRUSTED_FEEDS_FILE, [])
            if feed["url"] not in trusted:
                trusted.append(feed["url"])
                _write_json(TRUSTED_FEEDS_FILE, trusted)

        return {**saved, "trusted": bool(feed.get("trusted"))}

    def delete_feed(self, feed_url):
        feeds = [feed for feed in self.list_feeds() if feed.get("url") != feed_url]
        trusted = [url for url in _read_json(TRUSTED_FEEDS_FILE, []) if url != feed_url]
        _write_json(FEEDS_DB_FILE, [{k: v for k, v in item.items() if k != "trusted"} for item in feeds])
        _write_json(TRUSTED_FEEDS_FILE, trusted)
        return {"deleted": feed_url}

    def get_cache(self, cache_key):
        return _read_json(CACHE_FILE, {}).get(cache_key)

    def set_cache(self, cache_key, value):
        cache = _read_json(CACHE_FILE, {})
        cache[cache_key] = {"value": value, "updated_at": _now()}
        _write_json(CACHE_FILE, cache)
        return cache[cache_key]


class MongoPersistence:
    """MongoDB persistence with the same surface as JsonPersistence."""

    kind = "mongodb"

    def __init__(self, uri, db_name):
        from pymongo import MongoClient

        self.client = MongoClient(uri)
        self.db = self.client[db_name]

    def get_latest_briefing(self):
        briefing = self.db.briefings.find_one(sort=[("timestamp", -1)], projection={"_id": False})
        return briefing or _read_json(DATA_FILE, None)

    def save_briefing(self, briefing):
        doc = deepcopy(briefing)
        doc.setdefault("created_at", _now())
        self.db.briefings.insert_one(doc)
        for article in briefing.get("all_articles", []):
            link = article.get("link")
            if not link:
                continue
            self.db.articles.update_one(
                {"link": link},
                {"$set": {**article, "updated_at": _now()}},
                upsert=True,
            )
        _write_json(DATA_FILE, briefing)
        return briefing

    def get_job(self, job_id):
        return self.db.jobs.find_one({"id": job_id}, projection={"_id": False})

    def upsert_job(self, job):
        job = {**job, "updated_at": _now()}
        self.db.jobs.update_one({"id": job["id"]}, {"$set": job}, upsert=True)
        return job

    def append_job_event(self, job_id, event):
        self.db.jobs.update_one(
            {"id": job_id},
            {
                "$set": {"phase": event.get("phase"), "updated_at": _now()},
                "$push": {"events": event},
            },
            upsert=True,
        )
        return self.get_job(job_id)

    def list_feeds(self):
        feeds = list(self.db.feeds.find({}, projection={"_id": False}))
        if feeds:
            return feeds
        return JsonPersistence().list_feeds()

    def add_feed(self, feed):
        if self.db.feeds.find_one({"url": feed["url"]}):
            raise ValueError("This feed URL already exists.")
        saved = {
            "url": feed["url"],
            "name": feed["name"],
            "categories": feed.get("categories", []),
            "region": feed.get("region", "global"),
            "trusted": bool(feed.get("trusted")),
            "created_at": _now(),
        }
        self.db.feeds.insert_one(saved)
        saved.pop("_id", None)
        return saved

    def delete_feed(self, feed_url):
        self.db.feeds.delete_one({"url": feed_url})
        return {"deleted": feed_url}

    def get_cache(self, cache_key):
        return self.db.pipeline_cache.find_one({"key": cache_key}, projection={"_id": False})

    def set_cache(self, cache_key, value):
        doc = {"key": cache_key, "value": value, "updated_at": _now()}
        self.db.pipeline_cache.update_one({"key": cache_key}, {"$set": doc}, upsert=True)
        return doc


def get_persistence():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "rssaiagents")
    if uri:
        try:
            return MongoPersistence(uri, db_name)
        except Exception:
            return JsonPersistence()
    return JsonPersistence()
