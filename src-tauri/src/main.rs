// PDFportal — entry point.
// In release builds, don't open a console window next to the app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    pdfportal_lib::run();
}
