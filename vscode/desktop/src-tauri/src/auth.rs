use serde::Serialize;
use serde_json::{json, Value};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};

// User sign-in (2026-11-01): the desktop app previously had NO user login -
// the main chat ran as a hardcoded "Guest session" with local-only history.
// This module adds Supabase-backed user sign-in with a persisted session
// (same OS app-config pattern as the admin session fix) and registers the
// secure_* keystore commands that src/bridge/platform.ts always expected
// but were never registered in main.rs.

const SUPABASE_AUTH_URL: &str = "https://xtvkltzmberxekoamala.supabase.co/auth/v1";
const USER_SESSION_FILE: &str = "user_session.json";
const SECURE_STORE_FILE: &str = "secure_store.json";

#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct UserSession {
    access_token: String,
    refresh_token: String,
    email: String,
}

#[derive(Default)]
pub struct UserSessionState {
    session: Mutex<Option<UserSession>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UserLoginResult {
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    email: Option<String>,
}

fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .https_only(true)
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|_| "Could not initialize the secure user connection.".to_string())
}

fn supabase_anon_key() -> Result<String, String> {
    std::env::var("SUPREMEAI_SUPABASE_ANON_KEY").map_err(|_| {
        "User sign-in is not configured on this device (missing SUPREMEAI_SUPABASE_ANON_KEY).".to_string()
    })
}

fn config_dir_file(app: &AppHandle, name: &str) -> Option<std::path::PathBuf> {
    let dir = app.path().app_config_dir().ok()?;
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join(name))
}

// Persisted user session so restarts keep the user signed in.
// Kill switch: SUPREMEAI_DESKTOP_NO_PERSIST_SESSION=1 (shared with admin session).
fn persist_user_session(app: &AppHandle, session: &UserSession) {
    if std::env::var("SUPREMEAI_DESKTOP_NO_PERSIST_SESSION").is_ok() {
        return;
    }
    if let Some(path) = config_dir_file(app, USER_SESSION_FILE) {
        if let Ok(bytes) = serde_json::to_vec(session) {
            let _ = std::fs::write(path, bytes);
        }
    }
}

pub fn seed_user_session(state: &UserSessionState, session: UserSession) {
    if let Ok(mut current) = state.session.lock() {
        *current = Some(session);
    }
}

pub fn load_persisted_user_session(app: &AppHandle, state: &UserSessionState) {
    let Some(path) = config_dir_file(app, USER_SESSION_FILE) else { return };
    let Ok(bytes) = std::fs::read(&path) else { return };
    if let Ok(session) = serde_json::from_slice::<UserSession>(&bytes) {
        seed_user_session(state, session);
    }
}

#[tauri::command]
pub async fn user_login(
    app: AppHandle,
    email: String,
    password: String,
    state: State<'_, UserSessionState>,
) -> Result<UserLoginResult, String> {
    let email = email.trim().to_lowercase();
    if email.is_empty()
        || email.len() > 254
        || email.chars().any(char::is_control)
        || password.is_empty()
        || password.len() > 1024
    {
        return Err("Enter a valid email and password.".to_string());
    }

    let http = client()?;
    let key = supabase_anon_key()?;
    let response = http
        .post(format!("{SUPABASE_AUTH_URL}/token?grant_type=password"))
        .header("apikey", &key)
        .json(&json!({ "email": email, "password": password }))
        .send()
        .await
        .map_err(|_| "The SupremeAI authentication service could not be reached.".to_string())?;
    let status = response.status();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "The authentication service returned an unreadable response.".to_string())?;
    if !status.is_success() {
        return Err(match status.as_u16() {
            400 | 401 => "Invalid email or password.".to_string(),
            403 => "This account is not authorized for desktop sign-in.".to_string(),
            422 => "The sign-in request was incomplete. Check your details.".to_string(),
            429 => "Too many sign-in attempts. Wait a moment and try again.".to_string(),
            _ => "The authentication service returned an error. Please try again.".to_string(),
        });
    }
    let data: Value = serde_json::from_slice(&bytes)
        .map_err(|_| "The authentication service returned an unreadable response.".to_string())?;
    let access_token = data
        .get("access_token")
        .and_then(Value::as_str)
        .ok_or("The authentication service returned an invalid session.")?
        .to_string();
    let refresh_token = data
        .get("refresh_token")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let session_email = data
        .pointer("/user/email")
        .and_then(Value::as_str)
        .unwrap_or(&email)
        .to_string();
    let session = UserSession {
        access_token,
        refresh_token,
        email: session_email.clone(),
    };
    seed_user_session(&state, session.clone());
    persist_user_session(&app, &session);
    Ok(UserLoginResult {
        status: "authenticated".to_string(),
        email: Some(session_email),
    })
}

#[tauri::command]
pub async fn user_logout(app: AppHandle, state: State<'_, UserSessionState>) -> Result<(), String> {
    if let Ok(mut current) = state.session.lock() {
        *current = None;
    }
    let _ = config_dir_file(&app, USER_SESSION_FILE).map(|path| std::fs::remove_file(path));
    Ok(())
}

#[tauri::command]
pub async fn user_session(state: State<'_, UserSessionState>) -> Result<Option<String>, String> {
    Ok(state
        .session
        .lock()
        .map_err(|_| "The user session could not be read.".to_string())?
        .as_ref()
        .map(|session| session.email.clone()))
}

// ---------------------------------------------------------------------------
// Secure keystore: src/bridge/platform.ts (createSecureStore) has always
// invoked secure_get/secure_set/secure_remove on Tauri, but the commands were
// never registered, so every call failed. They live here now: a small JSON
// keystore in the OS app-config dir. Tokens never reach the WebView.
// ---------------------------------------------------------------------------
fn read_keystore(app: &AppHandle) -> serde_json::Map<String, Value> {
    config_dir_file(app, SECURE_STORE_FILE)
        .and_then(|path| std::fs::read(path).ok())
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default()
}

fn write_keystore(app: &AppHandle, store: serde_json::Map<String, Value>) -> Result<(), String> {
    let Some(path) = config_dir_file(app, SECURE_STORE_FILE) else {
        return Err("The secure store location could not be resolved.".to_string());
    };
    let bytes = serde_json::to_vec(&Value::Object(store))
        .map_err(|_| "The secure store could not be encoded.".to_string())?;
    std::fs::write(path, bytes).map_err(|_| "The secure store could not be saved.".to_string())
}

#[tauri::command]
pub fn secure_get(app: AppHandle, key: String) -> Result<Option<String>, String> {
    if key.is_empty() || key.len() > 256 {
        return Err("Invalid secure store key.".to_string());
    }
    Ok(read_keystore(&app).get(&key).and_then(Value::as_str).map(str::to_string))
}

#[tauri::command]
pub fn secure_set(app: AppHandle, key: String, value: String) -> Result<(), String> {
    if key.is_empty() || key.len() > 256 {
        return Err("Invalid secure store key.".to_string());
    }
    if value.len() > 65_536 {
        return Err("Value is too large for the secure store.".to_string());
    }
    let mut store = read_keystore(&app);
    store.insert(key, Value::String(value));
    write_keystore(&app, store)
}

#[tauri::command]
pub fn secure_remove(app: AppHandle, key: String) -> Result<(), String> {
    if key.is_empty() || key.len() > 256 {
        return Err("Invalid secure store key.".to_string());
    }
    let mut store = read_keystore(&app);
    store.remove(&key);
    write_keystore(&app, store)
}
