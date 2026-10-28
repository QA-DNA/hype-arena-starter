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
    report: Option<Value>,
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
            report: None,
            error: None,
            output: None,
        }
    }
}

type Shared = Arc<Mutex<Job>>;

#[derive(Clone)]
struct AppState {
    run: Shared,
    evaluation: Shared,
}

pub fn app() -> Router {
    Router::new()
        .route(
            "/",
            get(|| async { Html(include_str!("../../../apps/web/index.html")) }),
        )
        .route("/styles.css", get(styles))
        .route("/app.js", get(javascript))
        .route("/assets/stack.png", get(stack_png))
        .route("/assets/pipeline.png", get(pipeline_png))
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
        .route(
            "/api/evaluation",
            get(current_evaluation).post(start_evaluation),
        )
        .route("/api/demo-comparison", get(demo_comparison))
        .route("/downloads/demo-unlabelled.csv", get(demo_csv))
        .route("/downloads/demo-reference.csv", get(reference_csv))
        .route("/downloads/demo-comparison.csv", get(comparison_csv))
        .layer(DefaultBodyLimit::max(32 * 1024 * 1024))
        .layer(axum::middleware::map_response(security_headers))
        .with_state(AppState {
            run: Arc::new(Mutex::new(Job::default())),
            evaluation: Arc::new(Mutex::new(Job::default())),
        })
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

async fn start_run(State(state): State<AppState>, Json(request): Json<RunRequest>) -> Response {
    let shared = state.run;
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
        if job.status == "running"
            || state
                .evaluation
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .status
                == "running"
        {
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

async fn current_run(State(state): State<AppState>) -> Json<Job> {
    Json(state.run.lock().unwrap_or_else(|e| e.into_inner()).clone())
}

async fn download(State(state): State<AppState>) -> Response {
    let job = state.run.lock().unwrap_or_else(|e| e.into_inner());
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

async fn current_evaluation(State(state): State<AppState>) -> Json<Job> {
    Json(
        state
            .evaluation
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone(),
    )
}

async fn start_evaluation(State(state): State<AppState>) -> Response {
    let id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .to_string();
    {
        // Lock both stores in the same order in both POST handlers.
        let run = state.run.lock().unwrap_or_else(|e| e.into_inner());
        let mut evaluation = state.evaluation.lock().unwrap_or_else(|e| e.into_inner());
        if run.status == "running" || evaluation.status == "running" {
            return fail(
                StatusCode::CONFLICT,
                "A CPU job is already in progress. Wait for it to complete.",
            );
        }
        *evaluation = Job {
            id: id.clone(),
            status: "running".into(),
            progress: 5,
            stage: "Preparing hidden-label evaluation".into(),
            ..Job::default()
        };
    }
    let shared = state.evaluation;
    tokio::spawn(async move {
        let worker_state = shared.clone();
        let result = tokio::task::spawn_blocking(move || run_evaluation(&worker_state)).await;
        let error = match result {
            Ok(Ok(())) => None,
            Ok(Err(e)) => Some(e),
            Err(e) => Some(format!("Evaluation worker stopped: {e}")),
        };
        if let Some(error) = error {
            let mut job = shared.lock().unwrap_or_else(|e| e.into_inner());
            job.status = "error".into();
            job.stage = "Evaluation failed".into();
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

fn run_evaluation(shared: &Shared) -> Result<(), String> {
    let started = Instant::now();
    let practice = read_csv(PRACTICE)?;
    let lexicon: Value = serde_json::from_str(LEXICON).map_err(|e| e.to_string())?;
    log(
        shared,
        started,
        15,
        "Reference data loaded",
        "The test answers stay outside the model. Held-out texts and their duplicates are excluded from training.",
    );
    log(
        shared,
        started,
        25,
        "Training and predicting hidden rows",
        "Running a fresh forest with no test labels or test forms. Shared templates and facts may remain in training.",
    );
    let report = veridyct_core::engine::evaluate_holdout(&practice, &lexicon)?;
    log(
        shared,
        started,
        90,
        "Reference labels revealed",
        format!(
            "Compared {} predictions: {} correct, {} incorrect; {} predicted unsure.",
            report.test_rows, report.correct, report.incorrect, report.unsure
        ),
    );
    let value = serde_json::to_value(&report).map_err(|e| e.to_string())?;
    log(
        shared,
        started,
        100,
        "Evaluation complete",
        format!(
            "Accuracy {:.2}%; macro-F1 {:.3}; majority baseline {:.2}%.",
            report.accuracy * 100.0,
            report.macro_f1,
            report.majority_accuracy * 100.0
        ),
    );
    let mut job = shared.lock().unwrap_or_else(|e| e.into_inner());
    job.report = Some(value);
    job.status = "complete".into();
    job.summary = json!({"test_rows":report.test_rows,"accuracy":report.accuracy,"elapsed_ms":started.elapsed().as_millis()});
    Ok(())
}

const DEMO_CSV: &str = include_str!("../../../demos/reviewed-unlabelled.csv");
const DEMO_REFERENCE: &str = include_str!("../../../demos/llm-reference.json");

async fn demo_comparison() -> Response {
    let result = (|| -> Result<Value, String> {
        let mut value: Value = serde_json::from_str(DEMO_REFERENCE).map_err(|e| e.to_string())?;
        value["csv"] = json!(DEMO_CSV);
        value["rows"] = serde_json::to_value(read_csv(DEMO_CSV)?).map_err(|e| e.to_string())?;
        Ok(value)
    })();
    match result {
        Ok(value) => Json(value).into_response(),
        Err(e) => fail(StatusCode::INTERNAL_SERVER_ERROR, e),
    }
}

fn csv_download(filename: &'static str, body: String) -> Response {
    (
        [
            (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
            (header::CONTENT_DISPOSITION, filename),
        ],
        body,
    )
        .into_response()
}

async fn demo_csv() -> Response {
    csv_download(
        "attachment; filename=veridyct-demo-unlabelled.csv",
        DEMO_CSV.to_string(),
    )
}

async fn reference_csv() -> Response {
    csv_download(
        "attachment; filename=veridyct-llm-reference.csv",
        include_str!("../../../demos/llm-reference.csv").to_string(),
    )
}

async fn comparison_csv(State(state): State<AppState>) -> Response {
    let result = (|| -> Result<String, String> {
        let reference: Value = serde_json::from_str(DEMO_REFERENCE).map_err(|e| e.to_string())?;
        let rows = read_csv(DEMO_CSV)?;
        let job = state.run.lock().unwrap_or_else(|e| e.into_inner());
        if job.status != "complete"
            || job.results.len() != rows.len()
            || !rows.iter().all(|row| {
                job.results
                    .iter()
                    .any(|p| p.id == row.id && p.text == row.text)
            })
        {
            return Err(
                "Run the reviewed 20-row demo before downloading its model comparison.".into(),
            );
        }
        let mut writer = csv::Writer::from_writer(Vec::new());
        writer
            .write_record([
                "id",
                "text",
                "date",
                "model_label",
                "llm_reference",
                "agreement",
                "score_true",
                "score_false",
                "score_unsure",
                "reference_reason",
                "source_ids",
            ])
            .map_err(|e| e.to_string())?;
        for row in rows {
            let prediction = job
                .results
                .iter()
                .find(|p| p.id == row.id)
                .ok_or("Missing prediction")?;
            let annotation = reference["references"]
                .as_array()
                .ok_or("Missing references")?
                .iter()
                .find(|r| r["id"] == row.id)
                .ok_or("Missing annotation")?;
            let expected = annotation["expected"]
                .as_str()
                .ok_or("Missing reference label")?;
            writer
                .write_record([
                    row.id,
                    row.text,
                    row.date,
                    prediction.label.clone(),
                    expected.into(),
                    (prediction.label == expected).to_string(),
                    prediction.probabilities.p_true.to_string(),
                    prediction.probabilities.p_false.to_string(),
                    prediction.probabilities.p_unsure.to_string(),
                    annotation["reason"].as_str().unwrap_or_default().into(),
                    annotation["source_ids"].to_string(),
                ])
                .map_err(|e| e.to_string())?;
        }
        String::from_utf8(writer.into_inner().map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())
    })();
    match result {
        Ok(csv) => csv_download("attachment; filename=veridyct-model-vs-llm.csv", csv),
        Err(e) => fail(StatusCode::CONFLICT, e),
    }
}

async fn stack_png() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "image/png")],
        include_bytes!("../../../apps/web/assets/stack.png").as_slice(),
    )
}
async fn pipeline_png() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "image/png")],
        include_bytes!("../../../apps/web/assets/pipeline.png").as_slice(),
    )
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
            "/api/evaluation",
            "/api/demo-comparison",
            "/assets/stack.png",
            "/assets/pipeline.png",
            "/downloads/demo-unlabelled.csv",
            "/downloads/demo-reference.csv",
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

    #[tokio::test]
    async fn review_answers_stay_outside_runtime_input_and_cpu_jobs_are_exclusive() {
        let rows = read_csv(DEMO_CSV).unwrap();
        let references: Value = serde_json::from_str(DEMO_REFERENCE).unwrap();
        assert_eq!(rows.len(), 20);
        assert!(
            rows.iter()
                .all(|row| row.label.is_empty() && row.form.is_empty())
        );
        let answers = references["references"].as_array().unwrap();
        assert_eq!(answers.len(), 20);
        for row in &rows {
            assert!(answers.iter().any(|answer| answer["id"] == row.id));
        }
        let state = AppState {
            run: Arc::new(Mutex::new(Job::default())),
            evaluation: Arc::new(Mutex::new(Job {
                status: "running".into(),
                ..Job::default()
            })),
        };
        let response = start_run(
            State(state.clone()),
            Json(RunRequest {
                csv: Some(DEMO_CSV.into()),
                generate: false,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        assert_eq!(state.run.lock().unwrap().status, "idle");
        let response = comparison_csv(State(state.clone())).await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        state.evaluation.lock().unwrap().status = "idle".into();
        state.run.lock().unwrap().status = "running".into();
        let response = start_evaluation(State(state)).await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
    }
}
