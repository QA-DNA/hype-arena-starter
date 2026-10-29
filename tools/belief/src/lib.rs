//! Compile the staged production module without editing the root exports.
pub use veridyct_core::{claim_program, knowledge, model};
#[path = "../../../crates/core/src/belief.rs"]
pub mod belief;
