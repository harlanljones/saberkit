//! Python bindings for [`saberkit_core`].
//!
//! This crate is the only one that knows Python exists. It converts Arrow
//! arrays to plain floats, calls into the statistical core, and converts the
//! results back. No statistics are implemented here.

use pyo3::prelude::*;
use pyo3_arrow::input::AnyArray;
use pyo3_arrow::PyArray;

mod arrow_bridge;
mod error;

use arrow_bridge::{at, check_lengths, column, float_array};

/// On-base percentage for a single player.
#[pyfunction]
#[pyo3(name = "obp", signature = (h, bb, hbp, ab, sf))]
fn obp_scalar(h: f64, bb: f64, hbp: f64, ab: f64, sf: f64) -> Option<f64> {
    saberkit_core::rates::obp(h, bb, hbp, ab, sf)
}

/// On-base percentage across whole Arrow columns.
#[pyfunction]
#[pyo3(name = "obp_batch", signature = (h, bb, hbp, ab, sf))]
fn obp_batch(
    h: AnyArray,
    bb: AnyArray,
    hbp: AnyArray,
    ab: AnyArray,
    sf: AnyArray,
) -> PyResult<PyArray> {
    let (h, bb, hbp, ab, sf) = (
        column(h, "h")?,
        column(bb, "bb")?,
        column(hbp, "hbp")?,
        column(ab, "ab")?,
        column(sf, "sf")?,
    );

    check_lengths(&[
        ("h", h.len()),
        ("bb", bb.len()),
        ("hbp", hbp.len()),
        ("ab", ab.len()),
        ("sf", sf.len()),
    ])?;

    let values = (0..h.len())
        .map(
            |i| match (at(&h, i), at(&bb, i), at(&hbp, i), at(&ab, i), at(&sf, i)) {
                (Some(h), Some(bb), Some(hbp), Some(ab), Some(sf)) => {
                    saberkit_core::rates::obp(h, bb, hbp, ab, sf)
                }
                _ => None,
            },
        )
        .collect();

    Ok(float_array(values))
}

/// Slugging percentage for a single player.
#[pyfunction]
#[pyo3(name = "slg", signature = (h, doubles, triples, hr, ab))]
fn slg_scalar(h: f64, doubles: f64, triples: f64, hr: f64, ab: f64) -> Option<f64> {
    saberkit_core::rates::slg_from_hits(h, doubles, triples, hr, ab)
}

/// Slugging percentage across whole Arrow columns.
#[pyfunction]
#[pyo3(name = "slg_batch", signature = (h, doubles, triples, hr, ab))]
fn slg_batch(
    h: AnyArray,
    doubles: AnyArray,
    triples: AnyArray,
    hr: AnyArray,
    ab: AnyArray,
) -> PyResult<PyArray> {
    let (h, doubles, triples, hr, ab) = (
        column(h, "h")?,
        column(doubles, "doubles")?,
        column(triples, "triples")?,
        column(hr, "hr")?,
        column(ab, "ab")?,
    );

    check_lengths(&[
        ("h", h.len()),
        ("doubles", doubles.len()),
        ("triples", triples.len()),
        ("hr", hr.len()),
        ("ab", ab.len()),
    ])?;

    let values = (0..h.len())
        .map(|i| {
            match (
                at(&h, i),
                at(&doubles, i),
                at(&triples, i),
                at(&hr, i),
                at(&ab, i),
            ) {
                (Some(h), Some(d), Some(t), Some(hr), Some(ab)) => {
                    saberkit_core::rates::slg_from_hits(h, d, t, hr, ab)
                }
                _ => None,
            }
        })
        .collect();

    Ok(float_array(values))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("SaberError", m.py().get_type::<error::SaberError>())?;
    m.add_function(wrap_pyfunction!(obp_scalar, m)?)?;
    m.add_function(wrap_pyfunction!(obp_batch, m)?)?;
    m.add_function(wrap_pyfunction!(slg_scalar, m)?)?;
    m.add_function(wrap_pyfunction!(slg_batch, m)?)?;
    Ok(())
}
