# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2025-10-10

### Fixed

- stdout copy could be gone upon exiting

### Changed

- Better exit experience (immediate)

## [1.0.1] - 2025-10-09

### Fixed

- BOOT_ORDER line in EEPROM config was not replaced but duplicated (#41)
- Prevented a race condition showing error message when choosing provisioning
- Possible Crash on shutdown request (#39)
- `master_fs` file was not removed from `/data` (#43)

### Changed

- No more gathering at start of Provision: was if last gathering older than 1mn (#38)
- No more `init=` in cmdline so no more next boot to script (#43)

### Added

- Ability to exit to shell via Q key
- copy of read rpi-imager's stdout on /dev/shm (#40)

## [1.0.0] - 2025-09-09

### Added

- Initial version
