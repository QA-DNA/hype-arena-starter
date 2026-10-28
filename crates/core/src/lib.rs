//! Shared workspace metadata and offline text preprocessing.

pub mod extraction;

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
        phase: "foundation",
        solver_ready: false,
        target: "CPU · Linux amd64 · offline",
    }
}
