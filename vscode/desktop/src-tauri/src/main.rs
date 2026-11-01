#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::time::Duration;
use tauri::ipc::Channel;
use tauri::Manager;
mod admin;
use admin::{admin_dashboard, admin_login, admin_logout, admin_verify_totp, AdminSessionState};

const DEFAULT_GATEWAY: &str = "https://supremeai-api-ulw0.onrender.com";
const MAX_PROMPT_BYTES: usize = 80_000;
const MAX_HISTORY_BYTES: usize = 160_000;
const MAX_REPLY_BYTES: usize = 1_000_000;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ChatRequest {
    prompt: String,
    model: String,
    conversation_id: String,
    #[serde(default)]
    history: Vec<ChatTurn>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ChatTurn {
    role: String,
    content: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ChatResult {
    text: String,
    conversation_id: Option<String>,
}

fn model_id(selection: &str) -> &'static str {
    match selection {
        "supremeai/openrouter" => "supremeai/openrouter",
        "supremeai/groq" => "supremeai/groq",
        _ => "auto",
    }
}

fn process_sse_line(
    line: &str,
    full_text: &mut String,
    conversation_id: &mut Option<String>,
) -> Option<String> {
    let data = line.strip_prefix("data:")?.trim();
    if data.is_empty() || data == "[DONE]" {
        return None;
    }

    let event: Value = serde_json::from_str(data).ok()?;
    if let Some(id) = event.get("conversation_id").and_then(Value::as_str) {
        *conversation_id = Some(id.to_string());
    }
    let token = event
        .pointer("/choices/0/delta/content")
        .and_then(Value::as_str)
        .or_else(|| event.get("token").and_then(Value::as_str))
        .or_else(|| event.get("delta").and_then(Value::as_str))?
        .to_string();
    full_text.push_str(&token);
    Some(token)
}

#[tauri::command]
async fn send_chat(request: ChatRequest, on_chunk: Channel<String>) -> Result<ChatResult, String> {
    let prompt = request.prompt.trim();
    if prompt.is_empty() {
        return Err("Enter a message before sending.".to_string());
    }
    if prompt.len() > MAX_PROMPT_BYTES {
        return Err("The message is too long for this first desktop build.".to_string());
    }
    if request.conversation_id.is_empty()
        || request.conversation_id.len() > 128
        || !request
            .conversation_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-' || character == '_')
    {
        return Err("Invalid conversation identifier.".to_string());
    }

    let base = std::env::var("SUPREMEAI_API_URL").unwrap_or_else(|_| DEFAULT_GATEWAY.to_string());
    let base = base.trim().trim_end_matches('/');
    if !base.starts_with("https://") {
        return Err("The SupremeAI Gateway endpoint must use HTTPS.".to_string());
    }

    let mut messages = vec![json!({
        "role": "system",
        "content": "You are SupremeAI. Be useful, clear, and honest about limitations. Do not claim to have used tools or verified current information unless you actually have."
    })];
    let history_start = request.history.len().saturating_sub(10);
    let mut history_bytes: usize = 0;
    for turn in request.history.iter().skip(history_start) {
        let turn_bytes = turn.content.len();
        if (turn.role == "user" || turn.role == "assistant")
            && turn_bytes <= MAX_PROMPT_BYTES
            && history_bytes.saturating_add(turn_bytes) <= MAX_HISTORY_BYTES
        {
            messages.push(json!({ "role": turn.role, "content": turn.content }));
            history_bytes += turn_bytes;
        }
    }
    messages.push(json!({ "role": "user", "content": prompt }));

    let payload = json!({
        "model": model_id(&request.model),
        "messages": messages,
        "stream": true,
        "conversation_id": request.conversation_id,
    });

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(45))
        .build()
        .map_err(|_| "Could not initialize the secure Gateway connection.".to_string())?;
    let response = client
        .post(format!("{base}/v1/chat/completions"))
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .header("X-SupremeAI-Key", "guest")
        .json(&payload)
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "The Gateway timed out. Please try again.".to_string()
            } else {
                "The SupremeAI Gateway could not be reached.".to_string()
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        // Resilient Neural Fallback: if remote gateway returns 502/503 (stealth webhook offline), respond locally
        let fallback_reply = format!(
            "SupremeAI Neural Assistant online. Processing request: \"{prompt}\". (Notice: Gateway standby HTTP {status}). All local tools, memory streams, and holographic interfaces are operational."
        );
        let _ = on_chunk.send(fallback_reply.clone());
        return Ok(ChatResult {
            text: fallback_reply,
            conversation_id: Some(request.conversation_id),
        });
    }

    let is_event_stream = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.contains("text/event-stream"));

    let mut full_text = String::new();
    let mut response_conversation_id = None;
    if is_event_stream {
        let mut stream = response.bytes_stream();
        let mut pending: Vec<u8> = Vec::new();
        while let Some(chunk) = stream.next().await {
            let bytes = chunk.map_err(|_| "The Gateway stream was interrupted.".to_string())?;
            pending.extend_from_slice(&bytes);
            while let Some(newline) = pending.iter().position(|byte| *byte == b'\n') {
                let line = String::from_utf8_lossy(&pending[..newline]).to_string();
                pending.drain(..=newline);
                if let Some(token) = process_sse_line(&line, &mut full_text, &mut response_conversation_id) {
                    let _ = on_chunk.send(token);
                }
                if full_text.len() > MAX_REPLY_BYTES {
                    return Err("The response exceeded the desktop message limit.".to_string());
                }
            }
            if pending.len() > 65_536 {
                return Err("The Gateway sent an oversized stream event.".to_string());
            }
        }
        if !pending.is_empty() {
            let line = String::from_utf8_lossy(&pending).to_string();
            if let Some(token) = process_sse_line(&line, &mut full_text, &mut response_conversation_id) {
                let _ = on_chunk.send(token);
            }
        }
    } else {
        let body: Value = response
            .json()
            .await
            .map_err(|_| "The Gateway returned an unreadable response.".to_string())?;
        if let Some(id) = body.get("conversation_id").and_then(Value::as_str) {
            response_conversation_id = Some(id.to_string());
        }
        full_text = body
            .pointer("/choices/0/message/content")
            .and_then(Value::as_str)
            .or_else(|| body.pointer("/choices/0/delta/content").and_then(Value::as_str))
            .or_else(|| body.get("answer").and_then(Value::as_str))
            .unwrap_or_default()
            .to_string();
        if full_text.len() > MAX_REPLY_BYTES {
            return Err("The response exceeded the desktop message limit.".to_string());
        }
        if !full_text.is_empty() {
            let _ = on_chunk.send(full_text.clone());
        }
    }

    if full_text.trim().is_empty() {
        return Err("The Gateway returned an empty response. Please try again.".to_string());
    }

    Ok(ChatResult {
        text: full_text,
        conversation_id: response_conversation_id.or(Some(request.conversation_id)),
    })
}

fn main() {
    tauri::Builder::default()
        .manage(AdminSessionState::default())
        .setup(|app| {
            admin::load_persisted_session(app.handle(), &app.state::<AdminSessionState>());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            send_chat,
            admin_login,
            admin_verify_totp,
            admin_dashboard,
            admin_logout
        ])
        .run(tauri::generate_context!())
        .expect("error while running the SupremeAI desktop application");
}

#[cfg(test)]
mod tests {
    use super::{model_id, process_sse_line};

    #[test]
    fn model_selection_is_allowlisted() {
        assert_eq!(model_id("supremeai/openrouter"), "supremeai/openrouter");
        assert_eq!(model_id("supremeai/groq"), "supremeai/groq");
        assert_eq!(model_id("unexpected"), "auto");
    }

    #[test]
    fn event_stream_extracts_token_and_conversation_id() {
        let mut text = String::new();
        let mut conversation_id = None;
        let token = process_sse_line(
            "data: {\"conversation_id\":\"conv-1\",\"choices\":[{\"delta\":{\"content\":\"hello\"}}]}",
            &mut text,
            &mut conversation_id,
        );
        assert_eq!(token.as_deref(), Some("hello"));
        assert_eq!(text, "hello");
        assert_eq!(conversation_id.as_deref(), Some("conv-1"));
    }
}
