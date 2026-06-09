import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { MongoClient } from "mongodb";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..", "..");
const briefingFile = path.join(rootDir, "briefing_data.json");
const feedsDbFile = path.join(rootDir, "feeds_db.json");
const trustedFeedsFile = path.join(rootDir, "feeds_default.json");

let mongoClient;
let mongoDb;

async function readJson(filePath, fallback) {
  try {
    const content = await fs.readFile(filePath, "utf8");
    return JSON.parse(content);
  } catch {
    return fallback;
  }
}

async function writeJson(filePath, data) {
  await fs.writeFile(filePath, JSON.stringify(data, null, 2));
}

export async function connectStore() {
  if (!process.env.MONGODB_URI) {
    return { kind: "json" };
  }

  mongoClient = new MongoClient(process.env.MONGODB_URI);
  await mongoClient.connect();
  mongoDb = mongoClient.db(process.env.MONGODB_DB || "rssaiagents");
  return { kind: "mongodb" };
}

export async function getLatestBriefing() {
  if (mongoDb) {
    const briefing = await mongoDb.collection("briefings").findOne({}, { sort: { timestamp: -1 }, projection: { _id: 0 } });
    if (briefing) return briefing;
  }
  return readJson(briefingFile, null);
}

export async function listFeeds() {
  if (mongoDb) {
    const feeds = await mongoDb.collection("feeds").find({}, { projection: { _id: 0 } }).toArray();
    if (feeds.length > 0) return feeds;
  }

  const feeds = await readJson(feedsDbFile, []);
  const trusted = new Set(await readJson(trustedFeedsFile, []));
  return feeds.map((feed) => ({ ...feed, trusted: trusted.has(feed.url) }));
}

export async function addFeed(feed) {
  if (mongoDb) {
    const existing = await mongoDb.collection("feeds").findOne({ url: feed.url });
    if (existing) {
      const error = new Error("This feed URL already exists.");
      error.statusCode = 409;
      throw error;
    }
    const saved = {
      url: feed.url,
      name: feed.name,
      categories: feed.categories || [],
      region: feed.region || "global",
      trusted: Boolean(feed.trusted),
      created_at: new Date().toISOString()
    };
    await mongoDb.collection("feeds").insertOne(saved);
    return saved;
  }

  const feeds = await listFeeds();
  if (feeds.some((existing) => existing.url === feed.url)) {
    const error = new Error("This feed URL already exists.");
    error.statusCode = 409;
    throw error;
  }

  const saved = {
    url: feed.url,
    name: feed.name,
    categories: feed.categories || [],
    region: feed.region || "global"
  };
  feeds.push(saved);
  await writeJson(feedsDbFile, feeds.map(({ trusted, ...item }) => item));

  if (feed.trusted) {
    const trusted = await readJson(trustedFeedsFile, []);
    if (!trusted.includes(feed.url)) {
      trusted.push(feed.url);
      await writeJson(trustedFeedsFile, trusted);
    }
  }

  return { ...saved, trusted: Boolean(feed.trusted) };
}

export async function deleteFeed(feedUrl) {
  if (mongoDb) {
    await mongoDb.collection("feeds").deleteOne({ url: feedUrl });
    return { deleted: feedUrl };
  }

  const feeds = await listFeeds();
  const trusted = await readJson(trustedFeedsFile, []);
  await writeJson(feedsDbFile, feeds.filter((feed) => feed.url !== feedUrl).map(({ trusted: _trusted, ...item }) => item));
  await writeJson(trustedFeedsFile, trusted.filter((url) => url !== feedUrl));
  return { deleted: feedUrl };
}
