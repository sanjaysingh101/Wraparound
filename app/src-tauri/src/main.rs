// Wraparound desktop shell.
//
// Responsibilities:
//  - open the webview window (React UI)
//  - spawn the local Python backend (FastAPI on 127.0.0.1:7345) as a child process
//    and terminate it when the app exits
//
// In development the backend is usually started separately (scripts/dev.sh); the
// shell only spawns it when nothing is listening on the port yet.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;

struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_ADDR: &str = "127.0.0.1:7345";

fn backend_running() -> bool {
    TcpStream::connect(BACKEND_ADDR).is_ok()
}

fn spawn_backend() -> Option<Child> {
    if backend_running() {
        return None;
    }
    // Resolve the backend launcher relative to the executable (packaged app) or the
    // repository layout (development).
    let exe = std::env::current_exe().ok()?;
    let candidates = [
        exe.parent()?.join("../Resources/backend"), // macOS bundle
        exe.parent()?.join("backend"),              // linux/windows bundle
        exe.parent()?.join("../../../../backend"),  // cargo target dir → repo root
    ];
    let backend_dir = candidates.iter().find(|p| p.join("pyproject.toml").exists())?;
    let python = backend_dir.join(".venv/bin/python");
    let python = if python.exists() {
        python
    } else {
        backend_dir.join(".venv/Scripts/python.exe")
    };
    Command::new(python)
        .args(["-m", "wraparound"])
        .current_dir(backend_dir)
        .spawn()
        .ok()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            use tauri::Manager;
            let child = spawn_backend();
            *app.state::<BackendProcess>().0.lock().unwrap() = child;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                use tauri::Manager;
                if let Some(mut child) = window
                    .app_handle()
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .unwrap()
                    .take()
                {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Wraparound");
}
