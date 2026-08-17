//! Bindings for the percentile engine.

use pyo3::prelude::*;
use pyo3::IntoPyObjectExt;
use pyo3_arrow::input::AnyArray;
use saberkit_core::percentile::{Direction, Scale, TiePolicy};

use crate::arrow_bridge::{column, float_array};
use crate::error::CoreError;
use crate::operand::{Numeric, Operand};

fn parse_direction(name: &str) -> PyResult<Direction> {
    match name {
        "higher_is_better" => Ok(Direction::HigherIsBetter),
        "lower_is_better" => Ok(Direction::LowerIsBetter),
        other => Err(crate::error::SaberError::new_err(format!(
            "unknown direction `{other}`: expected \"higher_is_better\" or \"lower_is_better\""
        ))),
    }
}

fn parse_tie(name: &str) -> PyResult<TiePolicy> {
    match name {
        "average" => Ok(TiePolicy::Average),
        "strict" => Ok(TiePolicy::Strict),
        "weak" => Ok(TiePolicy::Weak),
        other => Err(crate::error::SaberError::new_err(format!(
            "unknown tie policy `{other}`: expected \"average\", \"strict\", or \"weak\""
        ))),
    }
}

fn parse_scale(name: &str) -> PyResult<Scale> {
    match name {
        "continuous" => Ok(Scale::Continuous),
        "savant" => Ok(Scale::Savant),
        other => Err(crate::error::SaberError::new_err(format!(
            "unknown scale `{other}`: expected \"continuous\" or \"savant\""
        ))),
    }
}

/// Collect an Arrow column into the nullable values the core works with,
/// dropping rows that fail a playing-time qualifier.
fn population(
    values: AnyArray,
    qualifier: Option<AnyArray>,
    qualifier_min: Option<f64>,
) -> PyResult<Vec<Option<f64>>> {
    let values = column(values, "values")?;

    let Some(qualifier) = qualifier else {
        return Ok(values.iter().collect());
    };

    let qualifier = column(qualifier, "qualifier")?;
    if qualifier.len() != values.len() {
        return Err(crate::error::SaberError::new_err(format!(
            "length mismatch: `values` has {} elements but `qualifier` has {}",
            values.len(),
            qualifier.len()
        )));
    }

    let min = qualifier_min.unwrap_or(f64::NEG_INFINITY);
    Ok(values
        .iter()
        .zip(qualifier.iter())
        .map(|(value, playing_time)| match playing_time {
            Some(t) if t >= min => value,
            _ => None,
        })
        .collect())
}

/// A sorted population of values, ready for repeated percentile queries.
///
/// Build it once per metric per season and query it many times: construction
/// sorts, after which each lookup is a pair of binary searches.
#[pyclass(module = "saberkit._core", frozen)]
pub struct LeagueDistribution {
    inner: saberkit_core::LeagueDistribution,
}

#[pymethods]
impl LeagueDistribution {
    #[new]
    #[pyo3(signature = (
        values,
        *,
        direction = "higher_is_better",
        qualifier = None,
        qualifier_min = None,
        tie = "average",
    ))]
    fn new(
        values: AnyArray,
        direction: &str,
        qualifier: Option<AnyArray>,
        qualifier_min: Option<f64>,
        tie: &str,
    ) -> PyResult<Self> {
        let values = population(values, qualifier, qualifier_min)?;
        let inner = saberkit_core::LeagueDistribution::new(
            values,
            parse_direction(direction)?,
            parse_tie(tie)?,
        )
        .map_err(|e| PyErr::from(CoreError::from(e)))?;

        Ok(Self { inner })
    }

    /// Percentile of a value, or of every element of an array.
    #[pyo3(signature = (value, *, scale = "continuous"))]
    fn percentile_of(&self, py: Python<'_>, value: Numeric, scale: &str) -> PyResult<Py<PyAny>> {
        let scale = parse_scale(scale)?;
        let operand = Operand::resolve(value, "value")?;

        match operand.len() {
            None => operand
                .at(0)
                .and_then(|v| self.inner.percentile_of(v))
                .map(|p| scale.apply(p))
                .into_py_any(py),
            Some(n) => {
                let values = (0..n)
                    .map(|i| {
                        operand
                            .at(i)
                            .and_then(|v| self.inner.percentile_of(v))
                            .map(|p| scale.apply(p))
                    })
                    .collect();
                float_array(values).into_py_any(py)
            }
        }
    }

    /// The value standing at a given percentile — the inverse of
    /// [`Self::percentile_of`].
    fn value_at_percentile(&self, percentile: f64) -> Option<f64> {
        self.inner.value_at_percentile(percentile)
    }

    /// Number of qualified values in the distribution.
    #[getter]
    fn n(&self) -> usize {
        self.inner.len()
    }

    /// The best value in the population, in the metric's own units.
    #[getter]
    fn best(&self) -> f64 {
        self.inner.best()
    }

    /// The worst value in the population, in the metric's own units.
    #[getter]
    fn worst(&self) -> f64 {
        self.inner.worst()
    }

    /// Arithmetic mean of the population.
    #[getter]
    fn mean(&self) -> f64 {
        self.inner.mean()
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn __repr__(&self) -> String {
        let direction = match self.inner.direction() {
            Direction::HigherIsBetter => "higher_is_better",
            Direction::LowerIsBetter => "lower_is_better",
        };
        format!(
            "LeagueDistribution(n={}, direction={direction:?}, best={:.4}, worst={:.4})",
            self.inner.len(),
            self.inner.best(),
            self.inner.worst(),
        )
    }
}

/// Rank a population against itself, honouring a playing-time qualifier.
///
/// Players below `qualifier_min` are excluded from the distribution *and*
/// receive null — they neither get a rank nor distort anyone else's.
#[pyfunction]
#[pyo3(signature = (
    values,
    *,
    direction = "higher_is_better",
    qualifier = None,
    qualifier_min = None,
    tie = "average",
    scale = "continuous",
))]
pub fn percentile_ranks(
    values: AnyArray,
    direction: &str,
    qualifier: Option<AnyArray>,
    qualifier_min: Option<f64>,
    tie: &str,
    scale: &str,
) -> PyResult<pyo3_arrow::PyArray> {
    let values = population(values, qualifier, qualifier_min)?;

    let ranks = saberkit_core::percentile::percentile_ranks(
        &values,
        None,
        parse_direction(direction)?,
        parse_tie(tie)?,
        parse_scale(scale)?,
    )
    .map_err(|e| PyErr::from(CoreError::from(e)))?;

    Ok(float_array(ranks))
}
