use std::{env, fs, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=RUNTIME_BASELINE_SOURCE");
    println!("cargo:rerun-if-env-changed=RUNTIME_BASELINE_COMMIT");
    if env::var_os("CARGO_FEATURE_FROZEN_BASELINE").is_some() {
        let source = PathBuf::from(env::var("RUNTIME_BASELINE_SOURCE").expect(
            "frozen-baseline requires RUNTIME_BASELINE_SOURCE pointing to a preserved baseline structured.rs",
        ))
        .canonicalize()
        .expect("baseline source exists");
        println!("cargo:rerun-if-changed={}", source.display());
        let generated = format!(
            "#[path = {:?}] pub mod frozen_structured;\n",
            source.to_str().expect("UTF-8 path")
        );
        fs::write(
            PathBuf::from(env::var_os("OUT_DIR").expect("Cargo OUT_DIR")).join("frozen.rs"),
            generated,
        )
        .expect("write baseline module shim");
        println!(
            "cargo:rustc-env=RUNTIME_BASELINE_COMMIT={}",
            env::var("RUNTIME_BASELINE_COMMIT").unwrap_or_else(|_| "unspecified".into())
        );
    }
}
