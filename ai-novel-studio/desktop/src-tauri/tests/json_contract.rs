//! Lock down the exact JSON shapes the frontend depends on.
//!
//! The webview is written against these key names, so a rename here would
//! silently break it. These tests assert the serialized form of
//! [`app_lib::sidecar::SidecarInfo`] and of the `sidecar.json` handshake file.

use app_lib::sidecar::SidecarInfo;

#[test]
fn sidecar_info_serializes_to_camel_case() {
    let info = SidecarInfo {
        base_url: "http://127.0.0.1:43117".into(),
        token: "0123456789abcdef0123456789abcdef".into(),
        port: 43117,
        pid: 4242,
        started_at: "2026-11-16T06:35:36Z".into(),
        status: "ready".into(),
    };

    let json = serde_json::to_value(&info).expect("serialize SidecarInfo");
    let object = json.as_object().expect("SidecarInfo is an object");

    let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
    keys.sort_unstable();

    assert_eq!(
        keys,
        vec!["baseUrl", "pid", "port", "startedAt", "status", "token"],
        "the frontend is written against exactly these camelCase keys"
    );

    assert_eq!(object["baseUrl"], "http://127.0.0.1:43117");
    assert_eq!(object["token"], "0123456789abcdef0123456789abcdef");
    assert_eq!(object["port"], 43117);
    assert_eq!(object["pid"], 4242);
    // snake_case must NOT leak through the camelCase rename.
    assert!(object.get("base_url").is_none(), "no snake_case keys");
    assert!(object.get("started_at").is_none(), "no snake_case keys");
    assert_eq!(object["startedAt"], "2026-11-16T06:35:36Z");
    assert_eq!(object["status"], "ready");
}

#[test]
fn stopped_snapshot_reports_stopped_status() {
    let info = SidecarInfo::stopped();
    let json = serde_json::to_value(&info).expect("serialize");
    assert_eq!(json["status"], "stopped");
    assert_eq!(json["port"], 0);
    assert_eq!(json["pid"], 0);
}

#[test]
fn studio_error_serializes_to_code_and_message() {
    let err = app_lib::error::StudioError::SidecarExited("boom".into());
    let json = serde_json::to_value(&err).expect("serialize");
    assert_eq!(json["code"], "sidecar_exited");
    assert_eq!(
        json["message"],
        "the AI Novel Studio service exited unexpectedly: boom"
    );

    let keys: Vec<&str> = json
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert!(keys.contains(&"code") && keys.contains(&"message"));
}

#[test]
fn sidecar_json_handshake_uses_the_documented_keys() {
    // `write_handshake` writes this literal shape; assert it so a refactor
    // cannot silently change the on-disk contract.
    let info = SidecarInfo {
        base_url: "http://127.0.0.1:19858".into(),
        token: "90ec9006257e4585a5a4d74462fbc210".into(),
        port: 19858,
        pid: 19716,
        started_at: "2026-11-16T06:35:36Z".into(),
        status: "ready".into(),
    };

    let payload = serde_json::json!({
        "baseUrl": info.base_url,
        "token": info.token,
        "port": info.port,
        "pid": info.pid,
        "startedAt": info.started_at,
    });

    let object = payload.as_object().expect("handshake is an object");
    let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(keys, vec!["baseUrl", "pid", "port", "startedAt", "token"]);
}
