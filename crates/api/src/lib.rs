use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, State},
    http::{StatusCode, header},
    response::{Html, IntoResponse, Response},
    routing::{get, post},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    sync::{Arc, Mutex},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use veridyct_core::{
    Engine, GenerationReport, InputRow, Prediction, generate_claims, output_csv, read_csv,
};

const PRACTICE: &str = include_str!("../../../data/practice.csv");
const LEXICON: &str = include_str!("../../../data/lexicon.json");
const MAX_ROWS: usize = 30_000;

#[derive(Clone, Serialize)]
struct LogEntry {
    time: String,
    message: String,
}

#[derive(Clone, Serialize)]
struct Job {
    id: String,
    status: String,
    progress: u8,
    stage: String,
    logs: Vec<LogEntry>,
    results: Vec<Prediction>,
    generation: GenerationReport,
    summary: Value,
    error: Option<String>,
    #[serde(skip)]
    output: Option<String>,
}

impl Default for Job {
    fn default() -> Self {
        Self {
            id: String::new(),
            status: "idle".into(),
            progress: 0,
            stage: "Ready".into(),
            logs: vec![],
            results: vec![],
            generation: GenerationReport::default(),
            summary: json!({}),
            error: None,
            output: None,
        }
    }
}

type Shared = Arc<Mutex<Job>>;

pub fn app() -> Router {
    Router::new()
        .route(
            "/",
            get(|| async { Html(include_str!("../../../apps/web/index.html")) }),
        )
        .route("/styles.css", get(styles))
        .route("/app.js", get(javascript))
        .route(
            "/api/health",
            get(|| async { Json(json!({"status":"ok","service":"veridyct-api"})) }),
        )
        .route(
            "/api/workspace",
            get(|| async { Json(veridyct_core::workspace_info()) }),
        )
        .route(
            "/api/graph",
            get(|| async {
                (
                    [(header::CONTENT_TYPE, "application/json")],
                    include_str!("../../../docs/knowledge/graph.json"),
                )
            }),
        )
        .route("/api/dataset", get(dataset))
        .route("/api/runs", post(start_run))
        .route("/api/runs/current", get(current_run))
        .route("/api/runs/current/output.csv", get(download))
        .layer(DefaultBodyLimit::max(32 * 1024 * 1024))
        .layer(axum::middleware::map_response(security_headers))
        .with_state(Arc::new(Mutex::new(Job::default())))
}

fn fail(code: StatusCode, message: impl Into<String>) -> Response {
    (code, Json(json!({"error":message.into()}))).into_response()
}

async fn dataset() -> Response {
    match read_csv(PRACTICE) {
        Ok(rows) => {
            let assertions: usize = rows.iter().map(|r| r.form.len()).sum();
            Json(json!({"summary":{"rows":rows.len(),"assertions":assertions,"source":"Mihai · practice.csv + lexicon.json"},"rows":rows})).into_response()
        }
        Err(error) => fail(StatusCode::INTERNAL_SERVER_ERROR, error),
    }
}

#[derive(Deserialize)]
struct RunRequest {
    csv: Option<String>,
    #[serde(default = "default_generate")]
    generate: bool,
}
fn default_generate() -> bool {
    true
}

async fn start_run(State(shared): State<Shared>, Json(request): Json<RunRequest>) -> Response {
    let is_demo = request.csv.is_none();
    let mut rows = match read_csv(request.csv.as_deref().unwrap_or(PRACTICE)) {
        Ok(rows) => rows,
        Err(error) => return fail(StatusCode::UNPROCESSABLE_ENTITY, error),
    };
    if rows.is_empty() || rows.len() > MAX_ROWS {
        return fail(
            StatusCode::UNPROCESSABLE_ENTITY,
            format!("CSV must contain 1 to {MAX_ROWS} rows."),
        );
    }
    if is_demo {
        for (index, row) in rows.iter_mut().enumerate() {
            if index % 5 == 0 {
                row.label.clear();
            }
            row.form.clear();
        }
    }
    let id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .to_string();
    {
        let mut job = shared.lock().unwrap_or_else(|e| e.into_inner());
        if job.status == "running" {
            return fail(StatusCode::CONFLICT, "A run is already in progress.");
        }
        *job = Job {
            id: id.clone(),
            status: "running".into(),
            stage: "Input validated".into(),
            progress: 5,
            summary: json!({"rows":rows.len(),"demo":is_demo}),
            ..Job::default()
        };
    }
    let job_state = shared.clone();
    tokio::spawn(async move {
        let worker_state = job_state.clone();
        let result = tokio::task::spawn_blocking(move || {
            run_pipeline(&worker_state, rows, request.generate, is_demo)
        })
        .await;
        let error = match result {
            Ok(Ok(())) => None,
            Ok(Err(e)) => Some(e),
            Err(e) => Some(format!("Worker stopped: {e}")),
        };
        if let Some(error) = error {
            let mut job = job_state.lock().unwrap_or_else(|e| e.into_inner());
            job.status = "error".into();
            job.stage = "Run failed".into();
            job.error = Some(error.clone());
            job.logs.push(LogEntry {
                time: "error".into(),
                message: error,
            });
        }
    });
    (
        StatusCode::ACCEPTED,
        Json(json!({"id":id,"status":"running"})),
    )
        .into_response()
}

fn log(shared: &Shared, started: Instant, progress: u8, stage: &str, message: impl Into<String>) {
    let mut job = shared.lock().unwrap_or_else(|e| e.into_inner());
    job.progress = progress;
    job.stage = stage.into();
    job.logs.push(LogEntry {
        time: format!("{:.2}s", started.elapsed().as_secs_f64()),
        message: message.into(),
    });
}

fn run_pipeline(
    shared: &Shared,
    rows: Vec<InputRow>,
    generate: bool,
    demo: bool,
) -> Result<(), String> {
    let started = Instant::now();
    let practice = read_csv(PRACTICE)?;
    let lexicon: Value = serde_json::from_str(LEXICON).map_err(|e| e.to_string())?;
    log(
        shared,
        started,
        12,
        "Reference data loaded",
        format!(
            "Loaded {} practice rows and {} lexicon entities; no external services.",
            practice.len(),
            lexicon["subjects"].as_array().map_or(0, Vec::len)
        ),
    );
    let engine = Engine::new(&practice, &lexicon)?;
    log(
        shared,
        started,
        35,
        "Random Forest trained",
        "Seeded CPU forest ready; extracting subject, attribute and typed values.",
    );
    let predictions = engine.predict(&rows);
    let facts: usize = predictions.iter().map(|p| p.facts.len()).sum();
    log(
        shared,
        started,
        70,
        "Rows classified",
        format!(
            "Classified {} rows; extracted {facts} assertions with source references.",
            predictions.len()
        ),
    );
    let generation = if generate {
        let mut trusted = practice.clone();
        let existing: std::collections::BTreeSet<_> =
            practice.iter().map(|r| r.id.as_str()).collect();
        trusted.extend(
            rows.iter()
                .filter(|r| !existing.contains(r.id.as_str()))
                .cloned(),
        );
        generate_claims(&trusted, &predictions, &lexicon, 1000)?
    } else {
        GenerationReport::default()
    };
    log(
        shared,
        started,
        93,
        "MMR selection complete",
        format!(
            "Selected {} claims from {} evidenced candidates.",
            generation.claims.len(),
            generation.candidate_count
        ),
    );
    let output = output_csv(&predictions, &generation.claims)?;
    let known = rows.iter().filter(|r| !r.label.is_empty()).count();
    let mut counts = std::collections::BTreeMap::<String, usize>::new();
    for prediction in &predictions {
        *counts.entry(prediction.label.clone()).or_default() += 1;
    }
    let elapsed = started.elapsed().as_millis();
    log(
        shared,
        started,
        100,
        "Complete",
        format!(
            "Contract CSV ready: {} bytes, {} unknown rows, {} claims, {elapsed} ms.",
            output.len(),
            rows.len() - known,
            generation.claims.len()
        ),
    );
    let mut job = shared.lock().unwrap_or_else(|e| e.into_inner());
    job.results = predictions;
    job.generation = generation;
    job.output = Some(output);
    job.status = "complete".into();
    job.summary = json!({"rows":rows.len(),"known":known,"unknown":rows.len()-known,"assertions":facts,"elapsed_ms":elapsed,"model":"Seeded Random Forest · CPU","demo":demo,"counts":counts,"warning":if demo {"Practice demo includes training examples; scores are model estimates, not independent evaluation."} else {"Scores are model estimates. Extracted observations do not establish all temporal truth boundaries."}});
    Ok(())
}

async fn current_run(State(shared): State<Shared>) -> Json<Job> {
    Json(shared.lock().unwrap_or_else(|e| e.into_inner()).clone())
}

async fn download(State(shared): State<Shared>) -> Response {
    let job = shared.lock().unwrap_or_else(|e| e.into_inner());
    match &job.output {
        Some(csv) => (
            [
                (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
                (
                    header::CONTENT_DISPOSITION,
                    "attachment; filename=output.csv",
                ),
            ],
            csv.clone(),
        )
            .into_response(),
        None => fail(
            StatusCode::CONFLICT,
            "Run the pipeline successfully before downloading output.csv.",
        ),
    }
}

async fn styles() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/css; charset=utf-8")],
        include_str!("../../../apps/web/styles.css"),
    )
}
async fn javascript() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/javascript; charset=utf-8")],
        include_str!("../../../apps/web/app.js"),
    )
}

async fn security_headers(mut response: Response) -> Response {
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_SECURITY_POLICY,"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'".parse().unwrap());
    headers.insert(header::X_CONTENT_TYPE_OPTIONS, "nosniff".parse().unwrap());
    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{Body, to_bytes},
        http::Request,
    };
    use tower::ServiceExt;

    #[tokio::test]
    async fn local_routes_and_job_boundaries() {
        let router = app();
        for uri in [
            "/",
            "/styles.css",
            "/app.js",
            "/api/health",
            "/api/workspace",
            "/api/graph",
            "/api/dataset",
            "/api/runs/current",
        ] {
            let response = router
                .clone()
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK, "{uri}");
            assert!(
                response
                    .headers()
                    .contains_key(header::CONTENT_SECURITY_POLICY)
            );
        }
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/runs/current/output.csv")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::CONFLICT);
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/runs")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(r#"{"csv":"nonsense"}"#))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let body = to_bytes(response.into_body(), 4096).await.unwrap();
        assert!(serde_json::from_slice::<Value>(&body).unwrap()["error"].is_string());
    }
}
