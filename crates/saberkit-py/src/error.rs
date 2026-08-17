//! Python exception types.
//!
//! `saberkit-core`'s [`SaberError`](saberkit_core::SaberError) and pyo3's
//! `PyErr` are both foreign to this crate, so the orphan rule forbids a direct
//! `impl From<SaberError> for PyErr`. [`CoreError`] is the local newtype that
//! bridges them, which lets bindings use `?` on core calls.

use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

create_exception!(
    saberkit._core,
    SaberError,
    PyValueError,
    "Base class for every error raised by saberkit."
);

/// Newtype wrapper allowing `?` on `saberkit_core::Result` inside bindings.
pub struct CoreError(saberkit_core::SaberError);

impl From<saberkit_core::SaberError> for CoreError {
    fn from(err: saberkit_core::SaberError) -> Self {
        CoreError(err)
    }
}

impl From<CoreError> for PyErr {
    fn from(err: CoreError) -> PyErr {
        SaberError::new_err(err.0.to_string())
    }
}
