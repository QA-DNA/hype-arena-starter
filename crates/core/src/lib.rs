//! Shared offline CPU reasoning, provenance and competition output.

pub mod boosted;
pub mod claims;
pub mod engine;
pub mod extraction;
pub mod forest;
pub mod io;
pub mod knowledge;
pub mod model;
pub mod structured;
pub mod temporal;
mod typed;

pub use claims::generate_claims;
pub use engine::Engine;
pub use io::{output_csv, read_csv};
pub use model::*;

use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct WorkspaceInfo {
    pub name: &'static str,
    pub team: &'static str,
    pub version: &'static str,
    pub phase: &'static str,
    pub solver_ready: bool,
    pub target: &'static str,
}

pub fn workspace_info() -> WorkspaceInfo {
    WorkspaceInfo {
        name: "VERIDYCT",
        team: "JEV · Teo, Edi & Mihai",
        version: env!("CARGO_PKG_VERSION"),
        phase: "mvp",
        solver_ready: true,
        target: "CPU · Linux amd64 · offline",
    }
}
