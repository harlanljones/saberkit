//! Conversion between Arrow arrays and the plain `f64` values the core wants.
//!
//! Every binding funnels its inputs through [`column`] and its output through
//! [`float_array`], so null handling, dtype coercion and length validation are
//! defined in exactly one place.

use std::sync::Arc;

use arrow_array::builder::Float64Builder;
use arrow_array::{Array, ArrayRef, Float64Array};
use arrow_schema::DataType;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3_arrow::input::AnyArray;
use pyo3_arrow::PyArray;

/// Coerce an incoming Arrow object to a single contiguous `Float64Array`.
///
/// Inputs are taken as [`AnyArray`] rather than `PyArray` because the two
/// PyCapsule interfaces are not interchangeable: a `pyarrow.Array` exposes
/// `__arrow_c_array__`, but a `polars.Series` is chunked and exposes only
/// `__arrow_c_stream__`. Accepting both is what lets polars users call in
/// directly.
///
/// Integer and smaller-float columns are cast, since counting stats routinely
/// arrive as `Int64` or `Int32`. Non-numeric columns are rejected with a
/// `TypeError` naming the argument — Arrow *would* happily parse a `Utf8`
/// column into floats, but silently accepting strings hides real mistakes.
pub fn column(array: AnyArray, name: &'static str) -> PyResult<Float64Array> {
    let (chunks, _field) = array.into_chunked_array()?.into_inner();

    match chunks.len() {
        0 => Ok(Float64Array::from(Vec::<Option<f64>>::new())),
        // The overwhelmingly common case: one chunk, cast in place, no copy
        // beyond what the cast itself requires.
        1 => cast_f64(&chunks[0], name),
        _ => {
            let casted = chunks
                .iter()
                .map(|chunk| cast_f64(chunk, name))
                .collect::<PyResult<Vec<_>>>()?;

            let mut builder = Float64Builder::with_capacity(casted.iter().map(|a| a.len()).sum());
            for chunk in &casted {
                for value in chunk.iter() {
                    builder.append_option(value);
                }
            }
            Ok(builder.finish())
        }
    }
}

/// Cast a single Arrow array to `Float64`, preserving its null mask.
fn cast_f64(array: &ArrayRef, name: &'static str) -> PyResult<Float64Array> {
    let dtype = array.data_type();

    if matches!(dtype, DataType::Float64) {
        return Ok(array
            .as_any()
            .downcast_ref::<Float64Array>()
            .expect("Float64 data type implies Float64Array")
            .clone());
    }

    if !dtype.is_numeric() && !matches!(dtype, DataType::Null) {
        return Err(PyTypeError::new_err(format!(
            "argument `{name}` must be a numeric Arrow array, got {dtype}"
        )));
    }

    let cast = arrow_cast::cast(array.as_ref(), &DataType::Float64).map_err(|e| {
        PyTypeError::new_err(format!(
            "argument `{name}`: cannot cast {dtype} to float64: {e}"
        ))
    })?;

    Ok(cast
        .as_any()
        .downcast_ref::<Float64Array>()
        .expect("cast to Float64 yields Float64Array")
        .clone())
}

/// Read element `i`, returning `None` when it is null.
#[inline]
pub fn at(array: &Float64Array, i: usize) -> Option<f64> {
    array.is_valid(i).then(|| array.value(i))
}

/// Wrap computed values back into an Arrow array for return to Python.
pub fn float_array(values: Vec<Option<f64>>) -> PyArray {
    PyArray::from_array_ref(Arc::new(Float64Array::from(values)) as ArrayRef)
}
