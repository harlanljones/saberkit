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
            Ok(merge_chunks(&casted))
        }
    }
}

/// Concatenate already-cast chunks into one contiguous array, preserving nulls.
fn merge_chunks(casted: &[Float64Array]) -> Float64Array {
    let mut builder = Float64Builder::with_capacity(casted.iter().map(|a| a.len()).sum());
    for chunk in casted {
        for value in chunk.iter() {
            builder.append_option(value);
        }
    }
    builder.finish()
}

/// Cast a single Arrow array to `Float64`, preserving its null mask.
fn cast_f64(array: &ArrayRef, name: &'static str) -> PyResult<Float64Array> {
    let dtype = array.data_type();

    if matches!(dtype, DataType::Float64) {
        return Ok(array
            .as_any()
            .downcast_ref::<Float64Array>()
            // SAFETY: we just confirmed the DataType is Float64, so downcast
            // to Float64Array cannot fail. The `as_any()` + `downcast_ref()`
            // pattern is the standard Arrow path for this cast.
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
        // SAFETY: we explicitly cast to Float64 above, so the result is always
        // a Float64Array. Arrow's `cast()` returns `ArrayRef` but the concrete
        // type is determined by the target DataType we requested.
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

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::{Int32Array, StringArray};

    #[test]
    fn float64_passes_through_with_null_mask() {
        let arr = Arc::new(Float64Array::from(vec![Some(1.5), None, Some(3.0)])) as ArrayRef;
        let cast = cast_f64(&arr, "h").unwrap();
        assert_eq!(cast.len(), 3);
        assert!(cast.is_null(1));
        assert!(cast.is_valid(0) && cast.is_valid(2));
        assert_eq!(cast.value(2), 3.0);
    }

    #[test]
    fn integers_cast_preserving_nulls() {
        let arr = Arc::new(Int32Array::from(vec![Some(1), None, Some(3)])) as ArrayRef;
        let cast = cast_f64(&arr, "ab").unwrap();
        assert_eq!(cast.value(0), 1.0);
        assert!(cast.is_null(1));
        assert_eq!(cast.value(2), 3.0);
    }

    #[test]
    fn non_numeric_columns_are_rejected_by_name() {
        let arr = Arc::new(StringArray::from(vec![Some("a"), None])) as ArrayRef;
        let err = cast_f64(&arr, "h").unwrap_err();
        assert!(err.to_string().contains("`h`"));
        assert!(err.to_string().contains("Utf8"));
    }

    #[test]
    fn null_type_columns_cast_to_all_null() {
        let arr = Arc::new(arrow_array::NullArray::new(2)) as ArrayRef;
        let cast = cast_f64(&arr, "x").unwrap();
        assert_eq!(cast.len(), 2);
        assert!(cast.is_null(0) && cast.is_null(1));
    }

    #[test]
    fn merge_chunks_concatenates_and_preserves_nulls_across_boundaries() {
        let a = Float64Array::from(vec![Some(1.0), None]);
        let b = Float64Array::from(vec![None, Some(4.0)]);
        let merged = merge_chunks(&[a, b]);
        assert_eq!(merged.len(), 4);
        assert!(merged.is_valid(0));
        assert!(merged.is_null(1));
        assert!(merged.is_null(2));
        assert_eq!(merged.value(3), 4.0);
    }

    #[test]
    fn merge_empty_chunk_list_yields_empty_array() {
        let merged = merge_chunks(&[]);
        assert_eq!(merged.len(), 0);
    }
}
