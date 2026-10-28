use std::{env, net::SocketAddr};

#[tokio::main(worker_threads = 2)]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let address: SocketAddr = env::var("VERIDYCT_ADDR")
        .unwrap_or_else(|_| "127.0.0.1:8787".to_string())
        .parse()?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    eprintln!("VERIDYCT workspace → http://{}", listener.local_addr()?);
    eprintln!(
        "Foundation preview. The competition solver is not implemented. Ctrl+C stops the server."
    );
    axum::serve(listener, veridyct_api::app())
        .with_graceful_shutdown(shutdown())
        .await?;
    Ok(())
}

async fn shutdown() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    #[cfg(unix)]
    {
        if let Ok(mut terminate) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            tokio::select! { () = ctrl_c => {}, _ = terminate.recv() => {} }
        } else {
            ctrl_c.await;
        }
    }
    #[cfg(not(unix))]
    ctrl_c.await;
}
