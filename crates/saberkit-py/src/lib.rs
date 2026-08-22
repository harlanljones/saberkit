//! Python bindings for [`saberkit_core`].
//!
//! This crate is the only one that knows Python exists. It converts Arrow
//! arrays to plain floats, calls into the statistical core, and converts the
//! results back. No statistics are implemented here.
//!
//! Functions exposed on `_core` are positional and explicit; the friendly
//! signatures — keyword arguments, defaults, `LeagueContext` expansion — live
//! in the Python layer.

use pyo3::prelude::*;

mod arrow_bridge;
mod error;
mod league_py;
mod operand;
mod percentile_py;

use operand::{finish, output_len, Numeric, Operand};

/// Generate a binding whose core function returns `Option<f64>`.
///
/// Every argument accepts a scalar or an Arrow array; scalars broadcast, and an
/// all-scalar call returns a plain float instead of a one-element array.
macro_rules! stat {
    ($fname:ident, $pyname:literal, $core:expr, ($($arg:ident),+ $(,)?)) => {
        #[pyfunction]
        #[pyo3(name = $pyname, signature = ($($arg),+))]
        #[allow(clippy::too_many_arguments)]
        fn $fname(py: Python<'_>, $($arg: Numeric),+) -> PyResult<Py<PyAny>> {
            $(let $arg = Operand::resolve($arg, stringify!($arg))?;)+
            let len = output_len(&[$((stringify!($arg), &$arg)),+])?;

            let values = (0..len.unwrap_or(1))
                .map(|i| match ($($arg.at(i)),+) {
                    ($(Some($arg)),+) => ($core)($($arg),+),
                    _ => None,
                })
                .collect();

            finish(py, len, values)
        }
    };
}

/// As [`stat!`], for core functions that can fail (those parsing innings).
macro_rules! stat_fallible {
    ($fname:ident, $pyname:literal, $core:expr, ($($arg:ident),+ $(,)?)) => {
        #[pyfunction]
        #[pyo3(name = $pyname, signature = ($($arg),+))]
        #[allow(clippy::too_many_arguments)]
        fn $fname(py: Python<'_>, $($arg: Numeric),+) -> PyResult<Py<PyAny>> {
            $(let $arg = Operand::resolve($arg, stringify!($arg))?;)+
            let len = output_len(&[$((stringify!($arg), &$arg)),+])?;

            let values = (0..len.unwrap_or(1))
                .map(|i| -> PyResult<Option<f64>> {
                    match ($($arg.at(i)),+) {
                        ($(Some($arg)),+) => ($core)($($arg),+)
                            .map_err(|e| PyErr::from(error::CoreError::from(e))),
                        _ => Ok(None),
                    }
                })
                .collect::<PyResult<Vec<_>>>()?;

            finish(py, len, values)
        }
    };
}

// ---------------------------------------------------------------- rate stats

stat!(
    py_obp,
    "obp",
    saberkit_core::rates::obp,
    (h, bb, hbp, ab, sf)
);
stat!(py_avg, "avg", saberkit_core::rates::avg, (h, ab));
stat!(py_ops, "ops", saberkit_core::rates::ops, (obp, slg));
stat!(py_iso, "iso", saberkit_core::rates::iso, (slg, avg));
stat!(
    py_slg,
    "slg",
    saberkit_core::rates::slg_from_hits,
    (h, doubles, triples, hr, ab)
);
stat!(
    py_total_bases,
    "total_bases",
    |h, d, t, hr| Some(saberkit_core::rates::total_bases(h, d, t, hr)),
    (h, doubles, triples, hr)
);
stat!(
    py_singles,
    "singles",
    |h, d, t, hr| Some(saberkit_core::rates::singles(h, d, t, hr)),
    (h, doubles, triples, hr)
);
stat!(
    py_babip,
    "babip",
    saberkit_core::rates::babip,
    (h, hr, ab, k, sf)
);
stat!(
    py_woba,
    "woba",
    |singles, doubles, triples, hr, bb, ibb, hbp, ab, sf, w_bb, w_hbp, w_1b, w_2b, w_3b, w_hr| {
        let weights = saberkit_core::WobaWeights {
            w_bb,
            w_hbp,
            w_1b,
            w_2b,
            w_3b,
            w_hr,
        };
        saberkit_core::rates::woba(
            &weights, singles, doubles, triples, hr, bb, ibb, hbp, ab, sf,
        )
    },
    (singles, doubles, triples, hr, bb, ibb, hbp, ab, sf, w_bb, w_hbp, w_1b, w_2b, w_3b, w_hr)
);

stat_fallible!(py_era, "era", saberkit_core::rates::era, (er, ip));
stat_fallible!(
    py_fip,
    "fip",
    saberkit_core::rates::fip,
    (hr, bb, hbp, k, ip, c_fip)
);
stat_fallible!(
    py_xfip,
    "xfip",
    saberkit_core::rates::xfip,
    (fb, bb, hbp, k, ip, lg_hr_per_fb, c_fip)
);

// --------------------------------------------------------------- plus family

stat!(
    py_ops_plus,
    "ops_plus",
    saberkit_core::plus::ops_plus,
    (obp, slg, lg_obp, lg_slg, park_factor)
);
stat!(
    py_sops_plus,
    "sops_plus",
    saberkit_core::plus::sops_plus,
    (split_obp, split_slg, lg_split_obp, lg_split_slg)
);
stat!(
    py_tops_plus,
    "tops_plus",
    saberkit_core::plus::tops_plus,
    (split_obp, split_slg, total_obp, total_slg)
);
stat!(
    py_era_plus,
    "era_plus",
    saberkit_core::plus::era_plus,
    (era, lg_era, park_factor)
);
stat!(
    py_wraa,
    "wraa",
    saberkit_core::plus::wraa,
    (woba, pa, lg_woba, woba_scale)
);
stat!(
    py_wrc,
    "wrc",
    saberkit_core::plus::wrc,
    (woba, pa, lg_woba, woba_scale, lg_r_pa)
);
stat!(
    py_wrc_plus,
    "wrc_plus",
    saberkit_core::plus::wrc_plus,
    (woba, lg_woba, woba_scale, lg_r_pa, lg_wrc_pa, park_factor)
);

// -------------------------------------------------------------- minus family

stat!(
    py_era_minus,
    "era_minus",
    saberkit_core::minus::era_minus,
    (era, lg_era, park_factor)
);
stat!(
    py_fip_minus,
    "fip_minus",
    saberkit_core::minus::fip_minus,
    (fip, lg_fip, park_factor)
);
stat!(
    py_xfip_minus,
    "xfip_minus",
    saberkit_core::minus::xfip_minus,
    (xfip, lg_xfip, park_factor)
);

// ------------------------------------------------------- innings and Savant

/// Convert baseball innings notation (`190.2` = 190⅔) to a count of outs.
#[pyfunction]
fn ip_to_outs(ip: f64) -> PyResult<u32> {
    saberkit_core::ip::ip_to_outs(ip).map_err(|e| PyErr::from(error::CoreError::from(e)))
}

/// Convert a count of outs to true decimal innings.
#[pyfunction]
fn outs_to_innings(outs: u32) -> f64 {
    saberkit_core::ip::outs_to_innings(outs)
}

/// Minimum plate appearances for a batter to qualify on a Savant leaderboard.
#[pyfunction]
#[pyo3(signature = (team_games = saberkit_core::savant::FULL_SEASON_GAMES))]
fn batter_qualifier(team_games: f64) -> f64 {
    saberkit_core::savant::batter_qualifier(team_games)
}

/// Minimum batters faced for a pitcher to qualify on a Savant leaderboard.
#[pyfunction]
#[pyo3(signature = (team_games = saberkit_core::savant::FULL_SEASON_GAMES))]
fn pitcher_qualifier(team_games: f64) -> f64 {
    saberkit_core::savant::pitcher_qualifier(team_games)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("SaberError", m.py().get_type::<error::SaberError>())?;

    macro_rules! register {
        ($($f:ident),+ $(,)?) => { $(m.add_function(wrap_pyfunction!($f, m)?)?;)+ };
    }

    register!(
        py_obp,
        py_slg,
        py_avg,
        py_ops,
        py_iso,
        py_babip,
        py_total_bases,
        py_singles,
        py_woba,
        py_era,
        py_fip,
        py_xfip,
        py_ops_plus,
        py_sops_plus,
        py_tops_plus,
        py_era_plus,
        py_wraa,
        py_wrc,
        py_wrc_plus,
        py_era_minus,
        py_fip_minus,
        py_xfip_minus,
        ip_to_outs,
        outs_to_innings,
        batter_qualifier,
        pitcher_qualifier,
    );

    m.add_class::<percentile_py::LeagueDistribution>()?;
    m.add_function(wrap_pyfunction!(percentile_py::percentile_ranks, m)?)?;
    m.add_class::<league_py::LeagueTotals>()?;
    m.add_function(wrap_pyfunction!(league_py::season_context, m)?)?;

    Ok(())
}
