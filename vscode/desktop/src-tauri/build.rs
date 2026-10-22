fn main() {
    let manifest_dir = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let icon_path = manifest_dir.join("icons").join("icon.ico");
    if !icon_path.exists() {
        std::fs::create_dir_all(icon_path.parent().unwrap()).unwrap();
        let width: u32 = 32;
        let height: u32 = 32;
        let mut ico = Vec::new();
        ico.extend_from_slice(&[0u8, 0, 1, 0, 1, 0]);
        let and_row_bytes = (width + 31) / 32 * 4;
        let and_mask_size = and_row_bytes * height;
        let bytes_in_res: u32 = 40 + width * height * 4 + and_mask_size;
        let image_offset: u32 = 6 + 16;
        ico.push(width as u8);
        ico.push(height as u8);
        ico.push(0);
        ico.push(0);
        ico.extend_from_slice(&1u16.to_le_bytes());
        ico.extend_from_slice(&32u16.to_le_bytes());
        ico.extend_from_slice(&bytes_in_res.to_le_bytes());
        ico.extend_from_slice(&image_offset.to_le_bytes());
        ico.extend_from_slice(&40u32.to_le_bytes());
        ico.extend_from_slice(&width.to_le_bytes());
        ico.extend_from_slice(&(height * 2).to_le_bytes());
        ico.extend_from_slice(&1u16.to_le_bytes());
        ico.extend_from_slice(&32u16.to_le_bytes());
        ico.extend_from_slice(&0u32.to_le_bytes());
        ico.extend_from_slice(&(width * height * 4 + and_mask_size).to_le_bytes());
        ico.extend_from_slice(&0u32.to_le_bytes());
        ico.extend_from_slice(&0u32.to_le_bytes());
        ico.extend_from_slice(&0u32.to_le_bytes());
        ico.extend_from_slice(&0u32.to_le_bytes());
        for _y in 0..height {
            for _x in 0..width {
                ico.extend_from_slice(&[235u8, 99, 37, 255]);
            }
        }
        for _y in 0..height {
            for _b in 0..and_row_bytes {
                ico.push(0u8);
            }
        }
        std::fs::write(&icon_path, &ico).unwrap();
    }
    tauri_build::build()
}
