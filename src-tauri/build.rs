// Tauri's build step: embeds tauri.conf.json, the icon and the Windows
// application manifest into the executable.
fn main() {
    // Rebuild when the icons change. Without this, a redrawn icon
    // (npm run icon) silently kept the old one inside the .exe and the tray.
    println!("cargo:rerun-if-changed=icons");
    tauri_build::build()
}
