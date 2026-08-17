//! Innings pitched, which are not the decimal number they appear to be.
//!
//! Baseball records innings pitched in a notation where the digit after the
//! decimal point counts *outs*, not tenths: `190.1` means 190⅓ innings and
//! `190.2` means 190⅔. Treating those as decimals understates the denominator
//! by about 0.7%, which is enough to shift a FIP in the third decimal place and
//! quietly break any comparison against published figures.
//!
//! Every rate statistic with an innings denominator in this crate converts
//! through [`ip_to_innings`] first.

use crate::error::{Result, SaberError};

/// Convert baseball innings notation to a whole number of outs.
///
/// ```
/// # use saberkit_core::ip::ip_to_outs;
/// assert_eq!(ip_to_outs(190.2).unwrap(), 572);
/// assert_eq!(ip_to_outs(6.0).unwrap(), 18);
/// assert!(ip_to_outs(0.3).is_err());  // .3 is not valid notation
/// ```
pub fn ip_to_outs(ip: f64) -> Result<u32> {
    if !ip.is_finite() || ip < 0.0 {
        return Err(SaberError::InvalidInningsPitched { value: ip });
    }

    let whole = ip.trunc();
    // Multiplying the fraction by 10 and rounding absorbs the binary
    // representation error: 190.2 - 190.0 is 0.19999999999999998, not 0.2.
    let thirds = ((ip - whole) * 10.0).round();

    if !(0.0..=2.0).contains(&thirds) {
        return Err(SaberError::InvalidInningsPitched { value: ip });
    }

    Ok((whole as u32) * 3 + thirds as u32)
}

/// Convert a whole number of outs back to true decimal innings.
///
/// Note this is the *true* value (572 outs is 190.666…), not the `.1`/`.2`
/// display notation.
pub fn outs_to_innings(outs: u32) -> f64 {
    f64::from(outs) / 3.0
}

/// Convert baseball innings notation directly to true decimal innings.
///
/// This is the conversion every innings-denominated rate statistic needs:
/// `190.2` in, `190.666…` out.
pub fn ip_to_innings(ip: f64) -> Result<f64> {
    ip_to_outs(ip).map(outs_to_innings)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thirds_notation_converts_to_outs() {
        assert_eq!(ip_to_outs(190.0).unwrap(), 570);
        assert_eq!(ip_to_outs(190.1).unwrap(), 571);
        assert_eq!(ip_to_outs(190.2).unwrap(), 572);
        assert_eq!(ip_to_outs(0.0).unwrap(), 0);
        assert_eq!(ip_to_outs(0.1).unwrap(), 1);
    }

    #[test]
    fn invalid_fractions_are_rejected() {
        // .3 through .9 are not valid innings notation.
        for bad in [0.3, 1.5, 6.9, 190.4] {
            assert!(
                ip_to_outs(bad).is_err(),
                "{bad} should be rejected as innings notation"
            );
        }
    }

    #[test]
    fn negative_and_non_finite_are_rejected() {
        assert!(ip_to_outs(-1.0).is_err());
        assert!(ip_to_outs(f64::NAN).is_err());
        assert!(ip_to_outs(f64::INFINITY).is_err());
    }

    #[test]
    fn true_innings_differ_from_the_decimal_reading() {
        let innings = ip_to_innings(190.2).unwrap();
        assert!((innings - 190.666_666_666_666_67).abs() < 1e-12);
        // The naive reading would be 190.2 — a 0.24% error in the denominator.
        assert!((innings - 190.2).abs() > 0.4);
    }

    #[test]
    fn round_trips_through_outs() {
        assert!((outs_to_innings(572) - 190.0 - 2.0 / 3.0).abs() < 1e-12);
    }
}
