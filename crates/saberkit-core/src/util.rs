//! Small numeric helpers shared by every statistic.

/// Divide, returning `None` instead of infinity or NaN.
///
/// Every rate statistic in this crate funnels through here. A player with zero
/// at-bats has no batting average — that is missing data, not an error and not
/// infinity — so the whole library represents it as `None`, which the Python
/// layer surfaces as an Arrow null.
#[inline]
pub fn safe_div(numerator: f64, denominator: f64) -> Option<f64> {
    if denominator == 0.0 {
        return None;
    }
    finite(numerator / denominator)
}

/// Normalize NaN and ±infinity to `None`, leaving finite values untouched.
#[inline]
pub fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

/// Convert a park factor from the 100-scale to a plain ratio.
///
/// `saberkit` takes park factors on the 100-scale everywhere (100 = neutral),
/// because that is how both Baseball-Reference and FanGraphs publish them. Some
/// underlying formulas — notably wRC+ — are written in terms of a decimal
/// ratio, so they call this at the point of use.
#[inline]
pub fn pf_ratio(park_factor: f64) -> f64 {
    park_factor / 100.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_div_guards_zero_denominator() {
        assert_eq!(safe_div(1.0, 0.0), None);
        assert_eq!(safe_div(0.0, 0.0), None);
        assert_eq!(safe_div(3.0, 4.0), Some(0.75));
    }

    #[test]
    fn safe_div_rejects_non_finite_results() {
        assert_eq!(safe_div(f64::NAN, 1.0), None);
        assert_eq!(safe_div(f64::INFINITY, 1.0), None);
    }

    #[test]
    fn pf_ratio_converts_from_hundred_scale() {
        assert_eq!(pf_ratio(100.0), 1.0);
        assert_eq!(pf_ratio(105.0), 1.05);
    }
}
