//! Driver-independent input pipeline for the Rust rewrite.
//! No Python, ViGEmBus, hidapi, or Windows API dependency in the core.
//! A virtual XUSB backend is still required for actual Xbox emulation.
pub mod input;
pub mod mapping;
pub mod session;
