#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

#[tauri::command]
fn secure_get(_key: String) -> Result<Option<String>, String> {
    Err("secure storage is not configured for this build".to_string())
}

#[tauri::command]
fn secure_set(_key: String, _value: String) -> Result<(), String> {
    Err("secure storage is not configured for this build".to_string())
}

#[tauri::command]
fn secure_remove(_key: String) -> Result<(), String> {
    Err("secure storage is not configured for this build".to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![secure_get, secure_set, secure_remove])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
