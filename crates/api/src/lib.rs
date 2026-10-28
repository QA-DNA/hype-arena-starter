use axum::{
    Json, Router,
    http::header,
    response::{Html, IntoResponse},
    routing::get,
};
use serde_json::json;

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
            get(|| async { Json(json!({"status": "ok", "service": "veridyct-api"})) }),
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
        .layer(axum::middleware::map_response(security_headers))
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

async fn security_headers(mut response: axum::response::Response) -> axum::response::Response {
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_SECURITY_POLICY, "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'".parse().unwrap());
    headers.insert(header::X_CONTENT_TYPE_OPTIONS, "nosniff".parse().unwrap());
    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{Body, to_bytes},
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    #[tokio::test]
    async fn workspace_status_is_not_a_solver_success() {
        let response = app()
            .oneshot(
                Request::builder()
                    .uri("/api/workspace")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let data = to_bytes(response.into_body(), 4096).await.unwrap();
        let info: serde_json::Value = serde_json::from_slice(&data).unwrap();
        assert_eq!(info["solver_ready"], false);
    }

    #[tokio::test]
    async fn assets_work_without_external_services_and_unknown_routes_are_404() {
        for uri in ["/", "/styles.css", "/app.js", "/api/health", "/api/graph"] {
            let response = app()
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
        let response = app()
            .oneshot(
                Request::builder()
                    .uri("/missing")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
