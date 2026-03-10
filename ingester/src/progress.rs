//! Progress reporting for ingestion runs.
//!
//! Wraps `indicatif` so that callers can drive progress updates without
//! knowing the underlying rendering details. In test environments the bar
//! is hidden automatically when constructed with [`ProgressReporter::hidden`].

use indicatif::{ProgressBar, ProgressDrawTarget, ProgressStyle};

/// A thin wrapper around an `indicatif` progress bar used during ingestion.
pub struct ProgressReporter {
    bar: ProgressBar,
}

impl ProgressReporter {
    /// Create a visible progress bar for `total_files` files.
    pub fn new(total_files: u64) -> Self {
        let bar = ProgressBar::new(total_files);
        bar.set_style(
            ProgressStyle::with_template(
                "{spinner:.green} [{elapsed_precise}] [{wide_bar:.cyan/blue}] \
                 {pos}/{len} files  ({msg})",
            )
            .unwrap()
            .progress_chars("=>-"),
        );
        Self { bar }
    }

    /// Create a hidden (no-output) reporter for use in tests.
    pub fn hidden() -> Self {
        let bar = ProgressBar::with_draw_target(Some(0), ProgressDrawTarget::hidden());
        Self { bar }
    }

    /// Advance the bar by one file and display `records` as the status message.
    pub fn inc(&self, records: usize) {
        self.bar.set_message(format!("{records} records"));
        self.bar.inc(1);
    }

    /// Mark the bar as finished.
    pub fn finish(&self) {
        self.bar.finish_with_message("done");
    }
}
