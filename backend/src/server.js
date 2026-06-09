import "dotenv/config";
import cors from "cors";
import express from "express";
import {
  getPythonJob,
  startBriefingJob,
  startSearchJob
} from "./pythonWorkerClient.js";
import {
  addFeed,
  connectStore,
  deleteFeed,
  getLatestBriefing,
  listFeeds
} from "./store.js";

const app = express();
const port = Number(process.env.EXPRESS_PORT || 4000);
const allowedOrigins = (process.env.FRONTEND_ORIGIN || "http://127.0.0.1:5173,http://localhost:5173")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

app.use(cors({ origin: allowedOrigins }));
app.use(express.json({ limit: "1mb" }));

app.get("/api/health", async (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/api/briefings/run", async (req, res, next) => {
  try {
    const job = await startBriefingJob({
      algorithm: req.body.algorithm || "hdbscan",
      skip_fetch: Boolean(req.body.skip_fetch),
      time_window_hours: Number(req.body.time_window_hours || 24)
    });
    res.status(202).json(job);
  } catch (error) {
    next(error);
  }
});

app.post("/api/search/run", async (req, res, next) => {
  try {
    const query = String(req.body.query || "").trim();
    if (!query) {
      return res.status(400).json({ error: "Search query is required." });
    }
    const job = await startSearchJob({
      query,
      algorithm: req.body.algorithm || "hdbscan"
    });
    res.status(202).json(job);
  } catch (error) {
    next(error);
  }
});

app.get("/api/jobs/:id", async (req, res, next) => {
  try {
    res.json(await getPythonJob(req.params.id));
  } catch (error) {
    next(error);
  }
});

app.get("/api/jobs/:id/events", async (req, res) => {
  res.setHeader("content-type", "text/event-stream");
  res.setHeader("cache-control", "no-cache");
  res.setHeader("connection", "keep-alive");
  res.flushHeaders?.();

  let sentEvents = 0;
  let closed = false;

  req.on("close", () => {
    closed = true;
  });

  const send = (event) => {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  };

  const interval = setInterval(async () => {
    if (closed) {
      clearInterval(interval);
      return;
    }

    try {
      const job = await getPythonJob(req.params.id);
      const events = job.events || [];
      for (const event of events.slice(sentEvents)) {
        send(event);
      }
      sentEvents = events.length;

      if (["complete", "empty", "failed"].includes(job.status)) {
        send({ phase: job.status, timestamp: new Date().toISOString(), done: true });
        clearInterval(interval);
        res.end();
      }
    } catch (error) {
      send({ phase: "failed", timestamp: new Date().toISOString(), error: error.message, done: true });
      clearInterval(interval);
      res.end();
    }
  }, 1200);
});

app.get("/api/briefings/latest", async (_req, res, next) => {
  try {
    const briefing = await getLatestBriefing();
    if (!briefing) {
      return res.status(404).json({ error: "No briefing has been generated yet." });
    }
    res.json(briefing);
  } catch (error) {
    next(error);
  }
});

app.get("/api/feeds", async (_req, res, next) => {
  try {
    res.json(await listFeeds());
  } catch (error) {
    next(error);
  }
});

app.post("/api/feeds", async (req, res, next) => {
  try {
    const url = String(req.body.url || "").trim();
    const name = String(req.body.name || "").trim();
    if (!url || !name) {
      return res.status(400).json({ error: "Feed URL and name are required." });
    }

    const categories = Array.isArray(req.body.categories)
      ? req.body.categories
      : String(req.body.categories || "")
          .split(",")
          .map((category) => category.trim().toLowerCase())
          .filter(Boolean);

    const feed = await addFeed({
      url,
      name,
      categories,
      region: req.body.region || "global",
      trusted: Boolean(req.body.trusted)
    });
    res.status(201).json(feed);
  } catch (error) {
    next(error);
  }
});

app.delete("/api/feeds/:encodedUrl", async (req, res, next) => {
  try {
    res.json(await deleteFeed(decodeURIComponent(req.params.encodedUrl)));
  } catch (error) {
    next(error);
  }
});

app.use((error, _req, res, _next) => {
  res.status(error.statusCode || 502).json({ error: error.message || "Request failed." });
});

connectStore()
  .then((store) => {
    app.listen(port, () => {
      console.log(`Express API listening on http://127.0.0.1:${port} (${store.kind} persistence)`);
    });
  })
  .catch((error) => {
    console.error("Failed to start Express API:", error);
    process.exit(1);
  });
