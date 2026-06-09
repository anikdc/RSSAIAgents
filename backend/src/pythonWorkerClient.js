const PYTHON_WORKER_URL = process.env.PYTHON_WORKER_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${PYTHON_WORKER_URL}${path}`, {
    headers: {
      "content-type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.detail || body?.error || `Python worker returned ${response.status}`;
    throw new Error(message);
  }
  return body;
}

export function startBriefingJob(payload) {
  return request("/jobs/briefing", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function startSearchJob(payload) {
  return request("/jobs/search", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getPythonJob(jobId) {
  return request(`/jobs/${jobId}`);
}

export function getPythonLatestBriefing() {
  return request("/briefings/latest");
}
