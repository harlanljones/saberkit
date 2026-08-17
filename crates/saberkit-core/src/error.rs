//! Error type for the statistical core.
//!
//! The distinction this type draws is deliberate: a *missing* value (a player
//! with no at-bats) is not an error and never appears here — it is `None`.
//! These variants are for situations where the caller has misconfigured
//! something and a silent null would hide a bug.

use thiserror::Error;

/// Errors produced by `saberkit-core`.
#[derive(Debug, Error, Clone, PartialEq)]
pub enum SaberError {
    /// Two input arrays that must line up element-for-element did not.
    #[error("length mismatch: `{left_name}` has {left} elements but `{right_name}` has {right}")]
    LengthMismatch {
        /// Name of the first argument.
        left_name: &'static str,
        /// Length of the first argument.
        left: usize,
        /// Name of the second argument.
        right_name: &'static str,
        /// Length of the second argument.
        right: usize,
    },

    /// A league constant was missing, NaN, or outside a sane range.
    ///
    /// Unlike a null player row, a bad league constant poisons every result it
    /// touches, so it fails loudly rather than propagating.
    #[error("invalid league constant `{name}`: {reason}")]
    InvalidConstants {
        /// Name of the offending constant.
        name: &'static str,
        /// Why it was rejected.
        reason: String,
    },

    /// Innings pitched used a fractional part other than `.0`, `.1`, or `.2`.
    #[error(
        "invalid innings pitched `{value}`: the fraction must be .0, .1, or .2 \
         (baseball notation for 0, 1, or 2 outs)"
    )]
    InvalidInningsPitched {
        /// The rejected value.
        value: f64,
    },

    /// A percentile distribution had nothing in it to rank against.
    #[error("empty distribution: {reason}")]
    EmptyDistribution {
        /// Why the distribution ended up empty.
        reason: String,
    },
}

/// Convenience alias for fallible `saberkit-core` operations.
pub type Result<T> = std::result::Result<T, SaberError>;
