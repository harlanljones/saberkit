//! Unified handling of arguments that may be a scalar or an Arrow array.
//!
//! Every statistic accepts either form for every argument, so a caller can mix
//! them freely — a column of on-base percentages against a scalar league
//! average, with a per-row park factor:
//!
//! ```python
//! saberkit.ops_plus(df["obp"], df["slg"], lg_obp=0.312, lg_slg=0.399,
//!                   park_factor=df["park_factor"])
//! ```
//!
//! Scalars broadcast across the batch. If *every* argument is a scalar the
//! result is a plain float rather than a one-element array, which is what makes
//! a single Python function serve both the single-player and whole-league
//! cases.

use arrow_array::Float64Array;
use pyo3::prelude::*;
use pyo3::IntoPyObjectExt;
use pyo3_arrow::input::AnyArray;

use crate::arrow_bridge::{at, column, float_array};

/// An argument as it arrives from Python: a number or something Arrow-shaped.
#[derive(FromPyObject)]
pub enum Numeric {
    /// A plain Python number.
    Scalar(f64),
    /// Anything implementing the Arrow PyCapsule interface.
    Array(AnyArray),
}

/// An argument after conversion, ready to be indexed.
pub enum Operand {
    /// A single value, broadcast across every row.
    Scalar(f64),
    /// One value per row.
    Array(Float64Array),
}

impl Operand {
    /// Convert an incoming argument, casting Arrow input to `Float64`.
    pub fn resolve(value: Numeric, name: &'static str) -> PyResult<Self> {
        match value {
            Numeric::Scalar(v) => Ok(Operand::Scalar(v)),
            Numeric::Array(a) => Ok(Operand::Array(column(a, name)?)),
        }
    }

    /// Row count, or `None` for a scalar (which has no length of its own).
    pub fn len(&self) -> Option<usize> {
        match self {
            Operand::Scalar(_) => None,
            Operand::Array(a) => Some(a.len()),
        }
    }

    /// Read row `i`, returning `None` for a null.
    #[inline]
    pub fn at(&self, i: usize) -> Option<f64> {
        match self {
            Operand::Scalar(v) => v.is_finite().then_some(*v),
            Operand::Array(a) => at(a, i),
        }
    }
}

/// Determine the output length from a set of operands.
///
/// Returns `None` when every operand is a scalar, meaning the caller wants a
/// scalar back. Otherwise all array operands must agree on length.
pub fn output_len(operands: &[(&'static str, &Operand)]) -> PyResult<Option<usize>> {
    let mut agreed: Option<(&'static str, usize)> = None;

    for &(name, operand) in operands {
        let Some(len) = operand.len() else { continue };

        match agreed {
            None => agreed = Some((name, len)),
            Some((first_name, first_len)) if first_len != len => {
                return Err(crate::error::SaberError::new_err(format!(
                    "length mismatch: `{first_name}` has {first_len} elements \
                     but `{name}` has {len}"
                )));
            }
            Some(_) => {}
        }
    }

    Ok(agreed.map(|(_, len)| len))
}

/// Package results as a scalar or an Arrow array, matching the inputs.
pub fn finish(py: Python<'_>, len: Option<usize>, values: Vec<Option<f64>>) -> PyResult<Py<PyAny>> {
    match len {
        None => values.into_iter().next().flatten().into_py_any(py),
        Some(_) => float_array(values).into_py_any(py),
    }
}
