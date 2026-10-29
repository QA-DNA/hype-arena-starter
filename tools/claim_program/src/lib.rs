//! Isolated harness: compile the staged production source before root exports it.
mod model {
    pub use veridyct_core::Fact;
}
#[path = "../../../crates/core/src/claim_program.rs"]
pub mod claim_program;
#[path = "../../../crates/core/src/structured.rs"]
pub mod structured;
