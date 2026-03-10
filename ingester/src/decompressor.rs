//! File content reader with transparent gz decompression.
//!
//! Reads a file from the filesystem, automatically decompressing `.json.gz`
//! files on the fly. Plain `.json` files are read directly.

use anyhow::{Context, Result};
use flate2::bufread::GzDecoder;
use std::io::{BufRead, BufReader, Read};
use std::path::Path;

/// Read the full text content of a file, decompressing if the file ends in `.gz`.
///
/// # Errors
///
/// Returns an error if the file cannot be opened, read, or (for `.gz` files)
/// decompressed.
pub fn read_file_content(path: &Path) -> Result<String> {
    let file = std::fs::File::open(path)
        .with_context(|| format!("Failed to open file: {}", path.display()))?;
    let buf_reader = BufReader::with_capacity(8 * 1024 * 1024, file);

    if path.extension().and_then(|e| e.to_str()) == Some("gz") {
        read_gz(buf_reader, path)
    } else {
        read_plain(buf_reader, path)
    }
}

/// Decompress a gz-encoded stream and return its content as a `String`.
fn read_gz<R: BufRead>(reader: R, path: &Path) -> Result<String> {
    let mut decoder = GzDecoder::new(reader);
    let mut content = String::new();
    decoder
        .read_to_string(&mut content)
        .with_context(|| format!("Failed to decompress gz file: {}", path.display()))?;
    Ok(content)
}

/// Read a plain (non-compressed) stream and return its content as a `String`.
fn read_plain<R: BufRead>(mut reader: R, path: &Path) -> Result<String> {
    let mut content = String::new();
    reader
        .read_to_string(&mut content)
        .with_context(|| format!("Failed to read file: {}", path.display()))?;
    Ok(content)
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::Compression;
    use flate2::write::GzEncoder;
    use std::io::Write;
    use tempfile::NamedTempFile;

    /// Create a temporary `.gz` file containing the gz-compressed form of `content`.
    ///
    /// Uses `tempfile::Builder` to guarantee the `.gz` extension so that
    /// `read_file_content` triggers the decompression branch.
    fn create_temp_gz(content: &str) -> NamedTempFile {
        let tmp = tempfile::Builder::new().suffix(".gz").tempfile().unwrap();
        let file = std::fs::File::create(tmp.path()).unwrap();
        let mut encoder = GzEncoder::new(file, Compression::default());
        encoder.write_all(content.as_bytes()).unwrap();
        encoder.finish().unwrap();
        tmp
    }

    // Test #6: Read a `.json.gz` file and produce the decompressed JSON string.
    #[test]
    fn test_decompress_gz_file() {
        let expected = r#"{"Records":[]}"#;
        let tmp = create_temp_gz(expected);

        let result = read_file_content(tmp.path()).expect("Should decompress successfully");

        assert_eq!(result, expected);
    }

    // Test #7: `.json.gz` → decompress; `.json` → read directly.
    #[test]
    fn test_detect_gz_by_extension() {
        let content = r#"{"Records":[]}"#;

        // Plain .json file — must be read directly without decompression.
        let mut plain_tmp = tempfile::Builder::new().suffix(".json").tempfile().unwrap();
        plain_tmp.write_all(content.as_bytes()).unwrap();
        plain_tmp.flush().unwrap();

        let plain_result =
            read_file_content(plain_tmp.path()).expect("Should read plain file successfully");
        assert_eq!(plain_result, content);

        // Compressed .gz file — must be decompressed transparently.
        let gz_tmp = create_temp_gz(content);
        let gz_result =
            read_file_content(gz_tmp.path()).expect("Should decompress gz file successfully");
        assert_eq!(gz_result, content);
    }

    // Test #8: Corrupted gz file returns an error.
    #[test]
    fn test_decompress_invalid_gz_returns_error() {
        // Write random bytes that are NOT valid gzip data to a `.gz` file.
        let tmp = tempfile::Builder::new().suffix(".gz").tempfile().unwrap();
        std::fs::write(tmp.path(), b"this is not gzip data at all!!!").unwrap();

        let result = read_file_content(tmp.path());

        assert!(result.is_err(), "Corrupted gz file should return an error");
    }
}
