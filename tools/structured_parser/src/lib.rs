//! Isolated compile/test harness for the staged core module; no core integration edits.
mod model {
    pub use veridyct_core::Fact;
}
#[path = "../../../crates/core/src/structured.rs"]
pub mod structured;
