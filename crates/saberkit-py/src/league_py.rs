//! Bindings for [`saberkit_core::league::LeagueTotals`].
//!
//! This pyclass exists so that `LeagueContext.from_totals` can delegate every
//! derived rate — including `c_fip`, `lg_era`, and `lg_woba` — to the Rust
//! core, keeping the formula in one place.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use saberkit_core::league::WobaWeights;

use crate::error::CoreError;

/// Return a Python mapping for a bundled completed-season context.
///
/// This function only translates the core value into Python objects; the data,
/// population definition, and validation all live in `saberkit-core`.
#[pyfunction]
pub fn season_context(py: Python<'_>, season: u16) -> PyResult<Py<PyDict>> {
    let context = saberkit_core::LeagueContext::for_season(season).map_err(CoreError::from)?;
    let result = PyDict::new(py);
    result.set_item("season", context.season)?;
    result.set_item("lg_obp", context.lg_obp)?;
    result.set_item("lg_slg", context.lg_slg)?;
    result.set_item("lg_era", context.lg_era)?;
    result.set_item("lg_fip", context.lg_fip)?;
    result.set_item("lg_xfip", context.lg_xfip)?;
    result.set_item("lg_woba", context.lg_woba)?;
    result.set_item("woba_scale", context.woba_scale)?;
    result.set_item("c_fip", context.c_fip)?;
    result.set_item("lg_r_pa", context.lg_r_pa)?;
    result.set_item("lg_wrc_pa", context.lg_wrc_pa)?;
    result.set_item("lg_hr_per_fb", context.lg_hr_per_fb)?;

    let weights = context.require_weights().map_err(CoreError::from)?;
    let weights_dict = PyDict::new(py);
    weights_dict.set_item("w_bb", weights.w_bb)?;
    weights_dict.set_item("w_hbp", weights.w_hbp)?;
    weights_dict.set_item("w_1b", weights.w_1b)?;
    weights_dict.set_item("w_2b", weights.w_2b)?;
    weights_dict.set_item("w_3b", weights.w_3b)?;
    weights_dict.set_item("w_hr", weights.w_hr)?;
    result.set_item("weights", weights_dict)?;
    Ok(result.unbind())
}

/// Running totals of a league's counting stats.
///
/// League rates are computed by **summing the counting stats and then taking
/// the ratio**, never by averaging players' individual rates.
#[pyclass(module = "saberkit._core", frozen)]
pub struct LeagueTotals {
    inner: saberkit_core::league::LeagueTotals,
}

#[pymethods]
impl LeagueTotals {
    #[new]
    #[pyo3(signature = (
        *,
        ab = 0.0,
        h = 0.0,
        doubles = 0.0,
        triples = 0.0,
        hr = 0.0,
        bb = 0.0,
        ibb = 0.0,
        hbp = 0.0,
        sf = 0.0,
        k = 0.0,
        er = 0.0,
        outs = 0.0,
        r = 0.0,
        pa = 0.0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        ab: f64,
        h: f64,
        doubles: f64,
        triples: f64,
        hr: f64,
        bb: f64,
        ibb: f64,
        hbp: f64,
        sf: f64,
        k: f64,
        er: f64,
        outs: f64,
        r: f64,
        pa: f64,
    ) -> Self {
        Self {
            inner: saberkit_core::league::LeagueTotals {
                ab,
                h,
                doubles,
                triples,
                hr,
                bb,
                ibb,
                hbp,
                sf,
                k,
                er,
                outs,
                r,
                pa,
            },
        }
    }

    /// League on-base percentage from the summed totals.
    #[getter]
    fn lg_obp(&self) -> Option<f64> {
        self.inner.lg_obp()
    }

    /// League slugging percentage from the summed totals.
    #[getter]
    fn lg_slg(&self) -> Option<f64> {
        self.inner.lg_slg()
    }

    /// League earned run average from the summed totals.
    #[getter]
    fn lg_era(&self) -> Option<f64> {
        self.inner.lg_era()
    }

    /// The FIP constant that puts FIP on the ERA scale.
    ///
    /// Formula: `lgERA - (13·lgHR + 3·(lgBB + lgHBP) - 2·lgK) / lgIP`.
    /// This is the single source of truth — the Python layer calls into
    /// this rather than reimplementing the formula.
    #[getter]
    fn c_fip(&self) -> Option<f64> {
        self.inner.c_fip()
    }

    /// League runs per plate appearance.
    #[getter]
    fn lg_r_pa(&self) -> Option<f64> {
        self.inner.lg_r_pa()
    }

    /// League wOBA from the summed totals, given a season's linear weights.
    #[pyo3(signature = (w_bb, w_hbp, w_1b, w_2b, w_3b, w_hr))]
    #[allow(clippy::too_many_arguments)]
    fn lg_woba(
        &self,
        w_bb: f64,
        w_hbp: f64,
        w_1b: f64,
        w_2b: f64,
        w_3b: f64,
        w_hr: f64,
    ) -> Option<f64> {
        let weights = WobaWeights {
            w_bb,
            w_hbp,
            w_1b,
            w_2b,
            w_3b,
            w_hr,
        };
        self.inner.lg_woba(&weights)
    }

    fn __repr__(&self) -> String {
        format!(
            "LeagueTotals(ab={}, h={}, hr={}, bb={}, k={}, er={}, outs={}, r={}, pa={})",
            self.inner.ab,
            self.inner.h,
            self.inner.hr,
            self.inner.bb,
            self.inner.k,
            self.inner.er,
            self.inner.outs,
            self.inner.r,
            self.inner.pa,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn season_context_translates_core_values_and_weights() {
        Python::attach(|py| {
            let context = season_context(py, 2024).unwrap();
            let context = context.bind(py);
            let season = context
                .get_item("season")
                .unwrap()
                .unwrap()
                .extract::<u16>()
                .unwrap();
            let weights = context
                .get_item("weights")
                .unwrap()
                .unwrap()
                .cast_into::<PyDict>()
                .unwrap();
            let home_run = weights
                .get_item("w_hr")
                .unwrap()
                .unwrap()
                .extract::<f64>()
                .unwrap();
            assert_eq!(season, 2024);
            assert!(home_run > 2.0);
        });
    }
}
