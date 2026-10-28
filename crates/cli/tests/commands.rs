use std::process::Command;

#[test]
fn unfinished_solver_fails_explicitly() {
    let output = Command::new(env!("CARGO_BIN_EXE_veridyct"))
        .arg("run")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("not implemented"));
}

#[test]
fn info_is_machine_readable_and_honest() {
    let output = Command::new(env!("CARGO_BIN_EXE_veridyct"))
        .arg("info")
        .output()
        .unwrap();
    assert!(output.status.success());
    let info: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(info["solver_ready"], false);
}
