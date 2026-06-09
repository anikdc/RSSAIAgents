import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Database,
  Filter,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2
} from "lucide-react";
import "./styles.css";

const runtimeHost = typeof window !== "undefined" && window.location.hostname
  ? window.location.hostname
  : "127.0.0.1";
const API_BASE = import.meta.env.VITE_API_BASE || `http://${runtimeHost}:4000`;
const algorithms = ["hdbscan", "dbscan", "kmeans"];
const regions = ["global", "us", "uk", "europe", "india", "middle-east", "other"];
const categoryOptions = [
  "ai",
  "arts",
  "business",
  "climate",
  "conflict",
  "culture",
  "economy",
  "elections",
  "environment",
  "finance",
  "government",
  "health",
  "india",
  "markets",
  "medicine",
  "politics",
  "programming",
  "science",
  "security",
  "space",
  "sports",
  "startups",
  "technology",
  "world"
];

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "content-type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error || body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

async function optionalApi(path) {
  try {
    return await api(path);
  } catch (err) {
    if (/404/.test(err.message) || /No briefing has been generated/i.test(err.message)) {
      return null;
    }
    throw err;
  }
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asText(value) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return String(value);
}

function normalizeBriefing(value) {
  if (!value || typeof value !== "object") return null;
  return {
    ...value,
    trends: asArray(value.trends).map((trend, index) => ({
      ...trend,
      trend_id: trend?.trend_id ?? index + 1,
      briefing_type: asText(trend?.briefing_type || "Briefing"),
      briefing: asText(trend?.briefing),
      sources: asArray(trend?.sources)
    })),
    all_articles: asArray(value.all_articles)
  };
}

function phaseLabel(phase) {
  return String(phase || "idle")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function elapsedLabel(timestamp, startedAt) {
  if (!timestamp || !startedAt) {
    return "0s";
  }
  const elapsed = Math.max(0, Math.round((new Date(timestamp) - new Date(startedAt)) / 1000));
  return `${elapsed}s`;
}

function articleClusterId(article) {
  if (Number.isFinite(article.ui_trend_num) && article.ui_trend_num > 0) {
    return article.ui_trend_num;
  }
  if (Number.isFinite(article.cluster) && article.cluster >= 0) {
    return article.cluster + 1;
  }
  return -1;
}

function ClusterMap({ articles, isSearchBriefing }) {
  const [showNoise, setShowNoise] = useState(false);
  const hasNoise = (articles || []).some((article) => articleClusterId(article) === -1);
  const noiseToggleDisabled = isSearchBriefing || !hasNoise;
  const points = useMemo(() => {
    const minPlotX = 32;
    const maxPlotX = 268;
    const minPlotY = 32;
    const maxPlotY = 160;
    const withCoords = (articles || [])
      .filter((article) => Number.isFinite(article.x) && Number.isFinite(article.y))
      .map((article) => ({ ...article, clusterId: articleClusterId(article) }))
      .filter((article) => showNoise || article.clusterId !== -1);

    if (!withCoords.length) return [];
    const xs = withCoords.map((point) => point.x);
    const ys = withCoords.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spreadX = maxX - minX || 1;
    const spreadY = maxY - minY || 1;
    return withCoords.map((point) => ({
      ...point,
      cx: minPlotX + ((point.x - minX) / spreadX) * (maxPlotX - minPlotX),
      cy: minPlotY + ((point.y - minY) / spreadY) * (maxPlotY - minPlotY)
    }));
  }, [articles, showNoise]);

  const clusters = useMemo(() => {
    const clusterIds = new Set(points.map((point) => point.clusterId));
    return [...clusterIds].sort((a, b) => a - b);
  }, [points]);

  return (
    <div className="cluster-map-wrap">
      <div className="cluster-controls">
        <div className="cluster-legend">
          {clusters.filter((clusterId) => clusterId !== -1).map((clusterId) => (
            <span key={clusterId}>
              <i className={`cluster-swatch cluster-${clusterId % 6}`} />
              Cluster {clusterId}
            </span>
          ))}
          {clusters.includes(-1) && (
            <span>
              <i className="cluster-swatch cluster-noise" />
              Noise
            </span>
          )}
          {!clusters.length && <span>No clusters to plot</span>}
        </div>
        <button
          type="button"
          className={`toggle-button ${showNoise ? "active" : ""}`}
          disabled={noiseToggleDisabled}
          title={isSearchBriefing ? "Noise toggle is disabled for searched briefings." : "Show or hide noisy articles."}
          onClick={() => setShowNoise((current) => !current)}
        >
          Noise
        </button>
      </div>
      <svg className="cluster-map" viewBox="0 0 300 210" role="img" aria-label="Trend cluster map">
        <rect className="cluster-frame" x="16" y="16" width="268" height="160" rx="7" />
        {[0, 1, 2, 3, 4].map((tick) => (
          <g key={tick} className="cluster-grid">
            <line x1={16 + tick * 67} y1="16" x2={16 + tick * 67} y2="176" />
            <line x1="16" y1={16 + tick * 40} x2="284" y2={16 + tick * 40} />
          </g>
        ))}
        {points.map((point, index) => {
          const isNoise = point.clusterId === -1;
          return (
            <g key={`${point.link || point.title}-${index}`}>
              <circle
                cx={point.cx}
                cy={point.cy}
                r={isNoise ? 7 : 11}
                className={`cluster-point ${isNoise ? "cluster-noise" : `cluster-${point.clusterId % 6}`}`}
              >
                <title>{point.title}</title>
              </circle>
              {!isNoise && (
                <text x={point.cx} y={point.cy + 4} className="cluster-label">
                  {point.clusterId}
                </text>
              )}
            </g>
          );
        })}
        {!points.length && (
          <text x="150" y="101" className="cluster-empty-label">
            No cluster coordinates yet
          </text>
        )}
      </svg>
    </div>
  );
}

function ProgressRail({ job, events }) {
  const [expanded, setExpanded] = useState(true);
  const visibleEvents = events.filter((event) => event.phase !== "queued");
  const fallbackPhase = job?.phase || job?.status || "idle";
  const phase = visibleEvents.at(-1)?.phase || fallbackPhase;
  const startedAt = visibleEvents[0]?.timestamp || job?.started_at || job?.created_at;
  const hasProgress = Boolean(job?.id || visibleEvents.length);
  const fallbackTimestamp = job?.updated_at || job?.started_at || job?.created_at;
  return (
    <section className="panel progress-panel">
      <button type="button" className="progress-summary" onClick={() => setExpanded((current) => !current)}>
        <span className="panel-title">
          <Activity size={16} />
          <span>Pipeline</span>
        </span>
        <span className={`phase-pill phase-${phase}`}>{phaseLabel(phase)}</span>
        {hasProgress && <span className="progress-elapsed">{elapsedLabel(visibleEvents.at(-1)?.timestamp || fallbackTimestamp, startedAt)}</span>}
        {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {expanded && (
        <div className="event-list">
          {visibleEvents.slice(-8).map((event, index) => (
            <div className="event-row" key={`${event.phase}-${event.timestamp}-${index}`}>
              <span>{phaseLabel(event.phase)}</span>
              <time>{elapsedLabel(event.timestamp, startedAt)}</time>
            </div>
          ))}
          {hasProgress && !visibleEvents.length && (
            <div className="event-row">
              <span>{phaseLabel(phase)}</span>
              <time>{elapsedLabel(fallbackTimestamp, startedAt)}</time>
            </div>
          )}
          {!hasProgress && <div className="event-row"><span>No active run</span><time>0s</time></div>}
        </div>
      )}
    </section>
  );
}
function BriefingView({ briefing }) {
  const trends = briefing?.trends || [];
  return (
    <section className="briefing-column">
      <div className="section-heading">
        <h2>Trending Now</h2>
        {briefing?.timestamp && <span>{new Date(briefing.timestamp).toLocaleString()}</span>}
      </div>
      {!trends.length ? (
        <div className="empty-panel">No briefing data yet. Generate a briefing or run a search.</div>
      ) : (
        trends.map((trend) => (
          <article className="trend-card" key={trend.trend_id}>
            <header>
              <div>
                <span className="trend-kicker">Trend {trend.trend_id}</span>
                <h3>{trend.briefing_type}</h3>
              </div>
              <span className="source-count">{trend.trend_size || trend.sources?.length || 0} sources</span>
            </header>
            <div className="briefing-markdown">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />
                }}
              >
                {trend.briefing || ""}
              </ReactMarkdown>
            </div>
            <details>
              <summary>Sources</summary>
              <div className="source-list">
                {(trend.sources || []).map((source) => (
                  <a href={source.link} target="_blank" rel="noreferrer" key={source.link || source.title}>
                    <strong>{source.title || "Untitled"}</strong>
                    <span>{source.verification_status || "unknown"} - {source.source || "Unknown source"}</span>
                  </a>
                ))}
              </div>
            </details>
          </article>
        ))
      )}
    </section>
  );
}

function Sidebar({ briefing, feeds, onAddFeed, onDeleteFeed }) {
  const [feedForm, setFeedForm] = useState({
    url: "",
    name: "",
    categories: [],
    categoryDraft: categoryOptions[0],
    region: "global",
    trusted: false
  });
  const [feedQuery, setFeedQuery] = useState("");
  const [trustedOnly, setTrustedOnly] = useState(false);
  const [showFeedForm, setShowFeedForm] = useState(false);

  const rawFeed = briefing?.all_articles || [];
  const filteredFeeds = useMemo(() => {
    const query = feedQuery.trim().toLowerCase();
    return feeds.filter((feed) => {
      const haystack = [
        feed.name,
        feed.url,
        feed.region,
        ...(feed.categories || [])
      ].join(" ").toLowerCase();
      return (!trustedOnly || feed.trusted) && (!query || haystack.includes(query));
    });
  }, [feeds, feedQuery, trustedOnly]);

  function updateForm(field, value) {
    setFeedForm((current) => ({ ...current, [field]: value }));
  }

  async function submitFeed(event) {
    event.preventDefault();
    await onAddFeed(feedForm);
    setFeedForm({ url: "", name: "", categories: [], categoryDraft: categoryOptions[0], region: "global", trusted: false });
    setShowFeedForm(false);
  }

  function addCategory() {
    if (!feedForm.categoryDraft || feedForm.categories.includes(feedForm.categoryDraft)) {
      return;
    }
    updateForm("categories", [...feedForm.categories, feedForm.categoryDraft]);
  }

  function removeCategory(category) {
    updateForm("categories", feedForm.categories.filter((item) => item !== category));
  }

  return (
    <aside className="side-column">
      <section className="panel">
        <div className="panel-title">
          <Database size={16} />
          <span>Cluster Map</span>
        </div>
        <ClusterMap articles={rawFeed} isSearchBriefing={Boolean(briefing?.search_query)} />
      </section>

      <section className="panel">
        <div className="panel-title">
          <RefreshCw size={16} />
          <span>Raw Feed</span>
        </div>
        <div className="raw-feed">
          {rawFeed.slice(0, 12).map((article) => (
            <a href={article.link} target="_blank" rel="noreferrer" key={article.link || article.title}>
              <strong>{article.title || "Untitled"}</strong>
              <span>{article.source || "Unknown"} - {(article.published || "").slice(0, 16)}</span>
            </a>
          ))}
          {!rawFeed.length && <div className="empty-panel">No articles loaded.</div>}
        </div>
      </section>

      <section className="panel">
        <div className="feed-manager-head">
          <div className="panel-title">
            <Plus size={16} />
            <span>Feed Manager</span>
          </div>
          <span>{filteredFeeds.length} of {feeds.length}</span>
        </div>
        <div className="feed-tools">
          <div className="feed-search">
            <Search size={15} />
            <input value={feedQuery} onChange={(event) => setFeedQuery(event.target.value)} placeholder="Find feeds" />
          </div>
          <button
            type="button"
            className={`toggle-button ${trustedOnly ? "active" : ""}`}
            onClick={() => setTrustedOnly((current) => !current)}
          >
            <Filter size={14} /> Trusted
          </button>
        </div>
        <button type="button" className="add-feed-toggle" onClick={() => setShowFeedForm((current) => !current)}>
          <Plus size={16} /> {showFeedForm ? "Hide Form" : "Add Feed"}
        </button>
        {showFeedForm && (
          <form className="feed-form" onSubmit={submitFeed}>
            <input value={feedForm.url} onChange={(event) => updateForm("url", event.target.value)} placeholder="Feed URL" />
            <input value={feedForm.name} onChange={(event) => updateForm("name", event.target.value)} placeholder="Feed name" />
            <div className="category-picker">
              <select value={feedForm.categoryDraft} onChange={(event) => updateForm("categoryDraft", event.target.value)}>
                {categoryOptions.map((category) => <option key={category}>{category}</option>)}
              </select>
              <button type="button" className="ghost" onClick={addCategory}><Plus size={15} /> Category</button>
            </div>
            <div className="category-chips" aria-label="Selected categories">
              {feedForm.categories.map((category) => (
                <button type="button" key={category} onClick={() => removeCategory(category)}>
                  {category}
                </button>
              ))}
              {!feedForm.categories.length && <span>No categories selected</span>}
            </div>
            <select value={feedForm.region} onChange={(event) => updateForm("region", event.target.value)}>
              {regions.map((region) => <option key={region}>{region}</option>)}
            </select>
            <label className="check-row">
              <input type="checkbox" checked={feedForm.trusted} onChange={(event) => updateForm("trusted", event.target.checked)} />
              Trusted feed
            </label>
            <button type="submit"><Plus size={16} /> Save Feed</button>
          </form>
        )}
        <div className="feed-list">
          {filteredFeeds.map((feed) => (
            <div className="feed-row" key={feed.url}>
              <div>
                <div className="feed-name-line">
                  {feed.trusted && <span className="trusted-badge">trusted</span>}
                  <strong>{feed.name || "Unnamed"}</strong>
                </div>
                <span>{feed.region || "global"} - {(feed.categories || []).join(", ") || "uncategorized"}</span>
              </div>
              <button type="button" aria-label={`Delete ${feed.name}`} onClick={() => onDeleteFeed(feed.url)}>
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          {!filteredFeeds.length && <div className="empty-panel">No feeds match the current filter.</div>}
        </div>
      </section>
    </aside>
  );
}

function App() {
  const [briefing, setBriefing] = useState(null);
  const [feeds, setFeeds] = useState([]);
  const [algorithm, setAlgorithm] = useState("hdbscan");
  const [query, setQuery] = useState("");
  const [job, setJob] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [isSubmittingJob, setIsSubmittingJob] = useState(false);
  const completedJobIds = useRef(new Set());

  async function refreshData() {
    setError("");
    const [latest, feedList] = await Promise.all([
      optionalApi("/api/briefings/latest"),
      api("/api/feeds")
    ]);
    setBriefing(normalizeBriefing(latest));
    setFeeds(feedList);
  }

  useEffect(() => {
    refreshData().catch((err) => setError(err.message));
  }, []);

  function updateFromJobSnapshot(nextJob) {
    setJob(nextJob);
    setEvents(nextJob.events || []);
  }

  function startJobSnapshot(nextJob) {
    completedJobIds.current.delete(nextJob.id);
    updateFromJobSnapshot(nextJob);
  }

  function finishJob(finishedJob) {
    const jobId = typeof finishedJob === "string" ? finishedJob : finishedJob?.id;
    if (!jobId) return;
    if (completedJobIds.current.has(jobId)) return;
    completedJobIds.current.add(jobId);
    if (finishedJob?.result && ["complete", "empty"].includes(finishedJob.status)) {
      setBriefing(normalizeBriefing(finishedJob.result));
    }
    if (finishedJob?.status === "failed") {
      setError(finishedJob.error || "Pipeline job failed.");
    }
    setIsSubmittingJob(false);
    refreshData().catch((err) => setError(err.message));
  }

  useEffect(() => {
    if (!job?.id) return undefined;
    const source = new EventSource(`${API_BASE}/api/jobs/${job.id}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      setEvents((current) => [...current, event]);
      if (event.done) {
        source.close();
        api(`/api/jobs/${job.id}`)
          .then((nextJob) => {
            updateFromJobSnapshot(nextJob);
            finishJob(nextJob);
          })
          .catch(() => finishJob(job.id));
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [job?.id]);

  useEffect(() => {
    if (!job?.id || completedJobIds.current.has(job.id)) return undefined;
    let cancelled = false;
    let interval;

    async function pollJob() {
      try {
        const nextJob = await api(`/api/jobs/${job.id}`);
        if (cancelled) return;
        updateFromJobSnapshot(nextJob);
        if (["complete", "empty", "failed"].includes(nextJob.status)) {
          finishJob(nextJob);
          if (interval) {
            window.clearInterval(interval);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    pollJob();
    interval = window.setInterval(pollJob, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [job?.id]);

  async function startBriefing() {
    if (isSubmittingJob) return;
    setError("");
    setEvents([]);
    setIsSubmittingJob(true);
    try {
      const nextJob = await api("/api/briefings/run", {
        method: "POST",
        body: JSON.stringify({ algorithm, skip_fetch: false, time_window_hours: 24 })
      });
      startJobSnapshot(nextJob);
    } catch (err) {
      setIsSubmittingJob(false);
      setError(err.message);
    }
  }

  async function startSearch(event) {
    event.preventDefault();
    if (!query.trim() || isSubmittingJob) return;
    setError("");
    setEvents([]);
    setIsSubmittingJob(true);
    try {
      const nextJob = await api("/api/search/run", {
        method: "POST",
        body: JSON.stringify({ query: query.trim(), algorithm })
      });
      startJobSnapshot(nextJob);
    } catch (err) {
      setIsSubmittingJob(false);
      setError(err.message);
    }
  }

  async function addFeed(feed) {
    setError("");
    await api("/api/feeds", {
      method: "POST",
      body: JSON.stringify(feed)
    });
    await refreshData();
  }

  async function deleteFeed(feedUrl) {
    setError("");
    await api(`/api/feeds/${encodeURIComponent(feedUrl)}`, { method: "DELETE" });
    await refreshData();
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>AI News Briefing</h1>
          <p>Operational news intelligence from RSS, clustering, verification, and synthesis.</p>
        </div>
        <div className="toolbar">
          <select value={algorithm} onChange={(event) => setAlgorithm(event.target.value)} aria-label="Clustering algorithm">
            {algorithms.map((item) => <option key={item}>{item}</option>)}
          </select>
          <button type="button" onClick={startBriefing} disabled={isSubmittingJob}>
            <Play size={16} /> {isSubmittingJob ? "Running" : "Generate"}
          </button>
          <button type="button" className="ghost" onClick={refreshData} title="Reload latest briefing and feeds">
            <RefreshCw size={16} /> Reload
          </button>
        </div>
      </header>

      <form className="search-bar" onSubmit={startSearch}>
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search for a briefing topic" />
        <button type="submit" disabled={isSubmittingJob}>Search & Run</button>
      </form>

      {error && <div className="error-banner">{error}</div>}

      <div className="layout-grid">
        <div>
          <ProgressRail job={job} events={events} />
          <BriefingView briefing={briefing} />
        </div>
        <Sidebar briefing={briefing} feeds={feeds} onAddFeed={addFeed} onDeleteFeed={deleteFeed} />
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
