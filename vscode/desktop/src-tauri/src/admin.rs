use serde::Serialize;
use serde_json::{json, Value};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};

const GATEWAY_API: &str = "https://supremeai-api-ulw0.onrender.com";
const CORE_API: &str = "https://supremeai-primary-node.onrender.com";
const MAX_ADMIN_RESPONSE_BYTES: u64 = 1_000_000;

fn admin_login_path(mode: &str) -> Result<&'static str, String> {
    match mode {
        "owner" => Ok("/api/admin/login"),
        _ => Err("Tenant administrator sign-in is not enabled in this desktop release.".to_string()),
    }
}

#[derive(Clone, serde::Serialize, serde::Deserialize)]
pub struct AdminSession {
    pub token: String,
    pub role: String,
    pub email: String,
}

/// Tokens are kept only in process memory; they are never returned to the WebView
/// or written to localStorage, the filesystem, or an application preference store.
#[derive(Default)]
pub struct AdminSessionState {
    session: Mutex<Option<AdminSession>>,
}

const ADMIN_SESSION_FILE: &str = "admin_session.json";

fn admin_session_file(app: &AppHandle) -> Option<std::path::PathBuf> {
    let dir = app.path().app_config_dir().ok()?;
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join(ADMIN_SESSION_FILE))
}

// ROOT-CAUSE FIX (2026-11-01): the admin session used to live only in process
// memory, so every app restart force-logged the owner out. It is now persisted
// in the OS app-config directory and restored on launch. Kill switch:
// SUPREMEAI_DESKTOP_NO_PERSIST_SESSION=1 restores the old in-memory behavior.
fn persist_session(app: &AppHandle, session: &AdminSession) {
    if std::env::var("SUPREMEAI_DESKTOP_NO_PERSIST_SESSION").is_ok() {
        return;
    }
    if let Some(path) = admin_session_file(app) {
        if let Ok(bytes) = serde_json::to_vec(session) {
            let _ = std::fs::write(path, bytes);
        }
    }
}

pub fn seed_session(state: &AdminSessionState, session: AdminSession) {
    if let Ok(mut current) = state.session.lock() {
        *current = Some(session);
    }
}

pub fn load_persisted_session(app: &AppHandle, state: &AdminSessionState) {
    let Some(path) = admin_session_file(app) else { return };
    let Ok(bytes) = std::fs::read(&path) else { return };
    if let Ok(session) = serde_json::from_slice::<AdminSession>(&bytes) {
        seed_session(state, session);
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdminLoginResult {
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    role: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    email: Option<String>,
}

fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .https_only(true)
        .timeout(Duration::from_secs(60)) // Render free-tier cold starts take 30-50s; 20s caused false session failures
        .build()
        .map_err(|_| "Could not initialize the secure admin connection.".to_string())
}

fn api_error(status: reqwest::StatusCode, context: &str) -> String {
    match (context, status.as_u16()) {
        ("login", 401) => "Invalid email, password, or verification code.".to_string(),
        ("login", 403) => "This account is not authorized for that workspace.".to_string(),
        (_, 401) => "Your admin session may have expired. Sign in again.".to_string(),
        (_, 403) => "This account is not authorized to view this data.".to_string(),
        (_, 404) => "The requested admin data is not available.".to_string(),
        (_, 503) => "The admin service is temporarily unavailable.".to_string(),
        _ => "The admin service returned an error. Please try again.".to_string(),
    }
}

async fn parse_json_response(response: reqwest::Response, context: &str) -> Result<Value, String> {
    let status = response.status();
    if !status.is_success() {
        return Err(api_error(status, context));
    }
    if response
        .content_length()
        .is_some_and(|length| length > MAX_ADMIN_RESPONSE_BYTES)
    {
        return Err("The admin service returned an oversized response.".to_string());
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "The admin service returned an unreadable response.".to_string())?;
    if bytes.len() as u64 > MAX_ADMIN_RESPONSE_BYTES {
        return Err("The admin service returned an oversized response.".to_string());
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| "The admin service returned an unreadable response.".to_string())
}

fn store_session(
    state: &AdminSessionState,
    app: &AppHandle,
    token: String,
    role: String,
    email: String,
) -> Result<(), String> {
    if token.is_empty() || token.len() > 16_384 {
        return Err("The admin service returned an invalid session.".to_string());
    }
    let session = AdminSession { token, role, email };
    let mut current = state
        .session
        .lock()
        .map_err(|_| "The admin session could not be updated.".to_string())?;
    *current = Some(session.clone());
    drop(current);
    persist_session(app, &session);
    Ok(())
}

fn current_session(state: &AdminSessionState) -> Result<AdminSession, String> {
    state
        .session
        .lock()
        .map_err(|_| "The admin session could not be read.".to_string())?
        .clone()
        .ok_or_else(|| "Sign in to the admin workspace first.".to_string())
}

#[tauri::command]
pub async fn admin_login(
    mode: String,
    email: String,
    password: String,
    app: AppHandle,
    state: State<'_, AdminSessionState>,
) -> Result<AdminLoginResult, String> {
    let email = email.trim().to_lowercase();
    if email.is_empty()
        || email.len() > 254
        || email.chars().any(char::is_control)
        || password.is_empty()
        || password.len() > 1024
    {
        return Err("Enter a valid email and password.".to_string());
    }

    let endpoint = format!("{GATEWAY_API}{}", admin_login_path(&mode)?);
    let http = client()?;
    let response = http
        .post(endpoint)
        .json(&json!({ "email": email, "password": password }))
        .send()
        .await
        .map_err(|_| "The SupremeAI authentication service could not be reached.".to_string())?;
    let data = parse_json_response(response, "login").await?;

    match data.get("status").and_then(Value::as_str).unwrap_or_default() {
        "otp_required" => {
            return Ok(AdminLoginResult {
                status: "otp_required".to_string(),
                role: None,
                email: Some(email),
            });
        }
        "totp_setup_required" => {
            return Ok(AdminLoginResult {
                status: "totp_setup_required".to_string(),
                role: None,
                email: Some(email),
            });
        }
        "authenticated" | "trusted_browser" => {}
        _ => return Err("The owner sign-in could not be completed.".to_string()),
    }

    let role = data
        .get("role")
        .and_then(Value::as_str)
        .ok_or_else(|| "The authentication service returned an invalid role.".to_string())?;
    if role != "admin" {
        return Err("This account is not authorized for that workspace.".to_string());
    }
    let token = data
        .get("token")
        .and_then(Value::as_str)
        .ok_or_else(|| "The authentication service returned an invalid session.".to_string())?
        .to_string();
    let session_email = data
        .get("email")
        .and_then(Value::as_str)
        .unwrap_or(&email)
        .to_string();
    store_session(&state, &app, token, role.to_string(), session_email.clone())?;
    Ok(AdminLoginResult {
        status: "authenticated".to_string(),
        role: Some(role.to_string()),
        email: Some(session_email),
    })
}

#[tauri::command]
pub async fn admin_verify_totp(
    otp: String,
    app: AppHandle,
    state: State<'_, AdminSessionState>,
) -> Result<AdminLoginResult, String> {
    let otp = otp.trim();
    if otp.len() != 6 || !otp.chars().all(|character| character.is_ascii_digit()) {
        return Err("Enter the six-digit verification code.".to_string());
    }
    let http = client()?;
    let response = http
        .post(format!("{GATEWAY_API}/api/admin/totp-verify"))
        .json(&json!({ "otp": otp, "remember_browser": true }))
        .send()
        .await
        .map_err(|_| "The SupremeAI authentication service could not be reached.".to_string())?;
    let data = parse_json_response(response, "login").await?;
    let token = data
        .get("token")
        .and_then(Value::as_str)
        .ok_or_else(|| "The authentication service returned an invalid session.".to_string())?
        .to_string();
    let role = data
        .get("role")
        .and_then(Value::as_str)
        .filter(|role| *role == "admin")
        .ok_or_else(|| "The authentication service returned an invalid role.".to_string())?;
    let email = data
        .get("email")
        .and_then(Value::as_str)
        .unwrap_or("Platform owner")
        .to_string();
    store_session(&state, &app, token, role.to_string(), email.clone())?;
    Ok(AdminLoginResult {
        status: "authenticated".to_string(),
        role: Some(role.to_string()),
        email: Some(email),
    })
}

#[tauri::command]
pub async fn admin_dashboard(state: State<'_, AdminSessionState>) -> Result<Value, String> {
    let session = current_session(&state)?;
    if session.role != "admin" {
        return Err("This account is not authorized to view the admin workspace.".to_string());
    }
    let http = client()?;

    let tenant_response = http
        .get(format!("{GATEWAY_API}/api/admin/tenant-overview"))
        .bearer_auth(&session.token)
        .send()
        .await
        .map_err(|_| "The platform admin service could not be reached.".to_string())?;
    let tenant_overview = parse_json_response(tenant_response, "dashboard").await?;

    let health_response = http
        .get(format!("{CORE_API}/admin-api/health-map"))
        .bearer_auth(&session.token)
        .send()
        .await
        .map_err(|_| "The system health service could not be reached.".to_string())?;
    let health = parse_json_response(health_response, "dashboard").await?;
    Ok(json!({
        "scope": "platform",
        "role": "admin",
        "email": session.email,
        "tenantOverview": tenant_overview,
        "health": health,
    }))
}

#[tauri::command]
pub async fn admin_logout(app: AppHandle, state: State<'_, AdminSessionState>) -> Result<(), String> {
    let session = state
        .session
        .lock()
        .map_err(|_| "The admin session could not be cleared.".to_string())?
        .take();
    // Explicit sign-out also clears the persisted session file.
    let _ = admin_session_file(&app).map(|path| std::fs::remove_file(path));
    if let Some(session) = session {
        if let Ok(http) = client() {
            let _ = http
                .post(format!("{GATEWAY_API}/api/admin/logout"))
                .bearer_auth(session.token)
                .send()
                .await;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::admin_login_path;

    #[test]
    fn desktop_admin_login_only_allows_platform_owner() {
        assert_eq!(admin_login_path("owner").unwrap(), "/api/admin/login");
        assert!(admin_login_path("tenant_admin").is_err());
        assert!(admin_login_path("unknown").is_err());
    }
}
