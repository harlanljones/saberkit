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
//! - Misconfiguration — a NaN league constant, mismatched array lengths —
//!   raises [`SaberError`] rather than propagating a null.

#![forbid(unsafe_code)]
#![deny(missing_docs)]

pub mod error;
pub mod rates;
pub mod util;

pub use error::{Result, SaberError};
