//! Link configuration.
//!
//! In normal builds (`extension-module` on) pyo3 handles everything: an
//! extension module must NOT link libpython, since the interpreter loading it
//! provides those symbols.
//!
//! For the test harness (`cargo test -p saberkit-py --no-default-features`)
//! there is no host interpreter, so we must link libpython explicitly. pyo3
//! skips this under `abi3`, so we do it here from the interpreter's own
//! sysconfig values.

use std::process::Command;

fn main() {
    if std::env::var_os("CARGO_FEATURE_EXTENSION_MODULE").is_some() {
        return;
    }

    let python = std::env::var("PYO3_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let output = Command::new(&python)
        .args([
            "-c",
            "import sysconfig; print(sysconfig.get_config_var('LIBDIR')); \
             print(sysconfig.get_config_var('LDVERSION') or '')",
        ])
        .output()
        .unwrap_or_else(|e| panic!("failed to run `{python}` while configuring test link: {e}"));

    if !output.status.success() {
        panic!(
            "`{python}` failed while configuring test link: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    let lines = String::from_utf8_lossy(&output.stdout);
    let mut lines = lines.lines();
    let libdir = lines.next().expect("no LIBDIR from sysconfig");
    let ldversion = lines.next().expect("no LDVERSION from sysconfig");

    println!("cargo:rustc-link-search=native={libdir}");
    let lib = if ldversion.is_empty() {
        "python3".to_string()
    } else {
        format!("python{ldversion}")
    };
    println!("cargo:rustc-link-lib=dylib={lib}");
    // The test binary runs outside any interpreter's environment, so it also
    // needs to find libpython at load time.
    println!("cargo:rustc-link-arg=-Wl,-rpath,{libdir}");
}
