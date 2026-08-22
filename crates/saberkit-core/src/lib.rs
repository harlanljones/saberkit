//! Sabermetrics primitives in pure Rust.
//!
//! This crate holds the statistics themselves — rate stats, the "plus" family
//! (OPS+, sOPS+, ERA+, wRC+), the FanGraphs "minus" family, and a percentile
//! engine for Baseball-Savant-style rankings. It deliberately depends on
//! nothing but `thiserror`: no Python, no Arrow, no I/O, no network. That keeps
//! `cargo test -p saberkit-core` fast and interpreter-free, and lets the crate
//! stand on its own for Rust consumers.
//!
//! Python bindings live in the sibling `saberkit-py` crate.
//!
//! # Conventions
//!
//! - Undefined results are `None`, never NaN, infinity, or an error. A player
//!   with zero at-bats has no batting average; that is missing data.
//! - Park factors are on the **100-scale** (100 = neutral) across the whole
//!   public API, matching how Baseball-Reference and FanGraphs publish them.
//! - Innings pitched use baseball's `.1`/`.2` notation for thirds; see
//!   [`ip`]. Reading them as decimals is a real and easy-to-miss bug.
//! - Misconfiguration — a NaN league constant, mismatched array lengths —
//!   raises [`SaberError`] rather than propagating a null.
//!
//! # Accuracy
//!
//! Statistics that depend only on their inputs (OBP, SLG, wOBA, FIP, sOPS+,
//! tOPS+) reproduce published figures exactly. Those involving park factors
//! (OPS+, ERA+, and the minus family) are approximations of the publishers'
//! internal pipelines, which use regressed multi-year park factors; expect
//! agreement to within a point or two. Each function's documentation says which
//! it is.

#![forbid(unsafe_code)]
#![deny(missing_docs)]

pub mod error;
pub mod ip;
pub mod league;
pub mod minus;
pub mod percentile;
pub mod plus;
pub mod rates;
pub mod savant;
pub mod season_constants;
pub mod util;

pub use error::{Result, SaberError};
pub use league::{LeagueContext, LeagueTotals, WobaWeights};
pub use percentile::{Direction, LeagueDistribution, Scale, TiePolicy};
