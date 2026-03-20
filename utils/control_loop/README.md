
# Custom Control Loop Library

## Overview

This guide explains how to build a custom control loop library from the C
version provided by DotBot-libs and integrate it with the simulator using FFI
(Foreign Function Interface).

## Building with CMake

### Prerequisites

- CMake 3.10 or higher
- C compiler (gcc, clang, or MSVC)

### Build Steps

```bash
cmake -DDOTBOT_LIBS_DIR=<path to DotBot-libs base directory> -DDOTBOT_VERSION=<DotBot version> -B build .
make -C build
```

This creates the `build/` subdirectory and generates there the
`libdotbot_control_loop.so` library file.

`DOTBOT_LIBS_DIR` variable must be set to tell the build system where to find
the dotbot control loop library.
If not set default value for `DOTBOT_VERSION` is 3.


3. The compiled shared library will be in the `build/` directory (`.so` on Linux,
`.dylib` on macOS, `.dll` on Windows).

## Integration with Simulator

### Configuration

Add your custom control loop library to `simulator_init_state.toml`:

```toml
[[robots]]
address = "DECAFBAD4B0B0AAA"
custom_control_loop_library = "/path/to/libdotbot_control_loop.so"
```

Each robot configuration can specify its own library independently.
