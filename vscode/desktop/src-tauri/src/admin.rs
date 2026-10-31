use serde::Serialize;
use serde_json::{json, Value};
use std::sync::Mutex;
use std::time::Duration;
use tauri::State;

const GATEWAY_API: &str = "https://supremeai-api-ulw0.onrender.com";
const CORE_API: &str = "https://supremeai-primary-node.onrender.com";
const MAX_ADMIN_RESPONSE_BYTES: u64 = 1_000_000;

#[derive(Clone)]
struct AdminSession {
    token: String,
    role: String,
    email: String,
}

/// Tokens are kept only in process memory; they are never returned to the WebView
/// or written to localStorage, the filesystem, or an application preference store.
#[derive(Default)]
pub struct AdminSessionState {
    session: Mutex<Option<AdminSession>>,
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
        .timeout(Duration::from_secs(20))
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

fn store_session(state: &AdminSessionState, token: String, role: String, email: String) -> Result<(), String> {
    if token.is_empty() || token.len() > 16_384 {
        return Err("The admin service returned an invalid session.".to_string());
    }
    let mut current = state
        .session
        .lock()
        .map_err(|_| "The admin session could not be updated.".to_string())?;
    *current = Some(AdminSession { token, role, email });
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

    let (endpoint, mode) = match mode.as_str() {
        "owner" => (format!("{GATEWAY_API}/api/admin/login"), "owner"),
        "tenant_admin" => (format!("{GATEWAY_API}/api/admin/tenant-login"), "tenant_admin"),
        _ => return Err("Choose a supported admin sign-in method.".to_string()),
    };
    let http = client()?;
    let response = http
        .post(endpoint)
        .json(&json!({ "email": email, "password": password }))
        .send()
        .await
        .map_err(|_| "The SupremeAI authentication service could not be reached.".to_string())?;
    let data = parse_json_response(response, "login").await?;

    if mode == "owner" {
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
    }

    let role = data
        .get("role")
        .and_then(Value::as_str)
        .ok_or_else(|| "The authentication service returned an invalid role.".to_string())?;
    let expected_role = if mode == "owner" { "admin" } else { "tenant_admin" };
    if role != expected_role {
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
    store_session(&state, token, role.to_string(), session_email.clone())?;
    Ok(AdminLoginResult {
        status: "authenticated".to_string(),
        role: Some(role.to_string()),
        email: Some(session_email),
    })
}

#[tauri::command]
pub async fn admin_verify_totp(
    otp: String,
    remember_device: Option<bool>,
    state: State<'_, AdminSessionState>,
) -> Result<AdminLoginResult, String> {
    let otp = otp.trim();
    if otp.len() != 6 || !otp.chars().all(|character| character.is_ascii_digit()) {
        return Err("Enter the six-digit verification code.".to_string());
    }
    let remember = remember_device.unwrap_or(true);
    let http = client()?;
    let response = http
        .post(format!("{GATEWAY_API}/api/admin/totp-verify"))
        .json(&json!({ "otp": otp, "remember_browser": remember }))
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
    store_session(&state, token, role.to_string(), email.clone())?;
    Ok(AdminLoginResult {
        status: "authenticated".to_string(),
        role: Some(role.to_string()),
        email: Some(email),
    })
}

#[tauri::command]
pub async fn admin_dashboard(state: State<'_, AdminSessionState>) -> Result<Value, String> {
    let session = current_session(&state)?;
    let http = client()?;
    if session.role == "tenant_admin" {
        let response = http
            .get(format!("{GATEWAY_API}/api/admin/tenant-dashboard"))
            .bearer_auth(&session.token)
            .send()
            .await
            .map_err(|_| "The tenant admin service could not be reached.".to_string())?;
        return parse_json_response(response, "dashboard").await;
    }
    if session.role != "admin" {
        return Err("This account is not authorized to view the admin workspace.".to_string());
    }

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
pub async fn admin_logout(state: State<'_, AdminSessionState>) -> Result<(), String> {
    let session = state
        .session
        .lock()
        .map_err(|_| "The admin session could not be cleared.".to_string())?
        .take();
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
