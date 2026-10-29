use std::{
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn missing_input_is_an_actionable_error() {
    let output = Command::new(env!("CARGO_BIN_EXE_veridyct"))
        .args(["run", "--input", "/veridyct-nonexistent-input.csv"])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("Cannot read"));
}

#[test]
fn info_is_machine_readable() {
    let output = Command::new(env!("CARGO_BIN_EXE_veridyct"))
        .arg("info")
        .output()
        .unwrap();
    assert!(output.status.success());
    let info: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(info["name"], "VERIDYCT");
}

#[test]
fn expired_deadline_does_not_publish_output() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("veridyct-expired-{unique}.csv"));
    let output = Command::new(env!("CARGO_BIN_EXE_veridyct"))
        .env("ARENA_DEADLINE", "1")
        .args(["run", "--output"])
        .arg(&path)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(!path.exists());
    assert!(String::from_utf8_lossy(&output.stderr).contains("deadline"));
}
