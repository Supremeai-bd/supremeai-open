#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

#[tauri::command]
fn secure_get(key: String) -> Option<String> {
    // OS vault integration placeholder
    None
}

#[tauri::command]
fn secure_set(key: String, value: String) -> Result<(), String> {
    let _ = (key, value);
    Ok(())
}

#[tauri::command]
fn secure_remove(key: String) -> Result<(), String> {
    let _ = key;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![secure_get, secure_set, secure_remove])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
