
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
cd utils/control_loop
cmake -DDOTBOT_LIBS_DIR=<path to DotBot-libs base directory> -B build .
make -C build
```

This creates the `build/` subdirectory and generates there the
`libdotbot_control_loop.so` library file.

`DOTBOT_LIBS_DIR` must be set to tell the build system where to find the
DotBot control loop source files.

### CMake Options

All options below are cache variables and can be set via the command line
(`-D<OPTION>=<value>`), `ccmake` (TUI), or `cmake-gui`.

| Option | Type | Default | Description |
|---|---|---|---|
| `DOTBOT_LIBS_DIR` | PATH | _(required)_ | Path to the DotBot-libs base directory |
| `DOTBOT_VERSION` | STRING | `3` | DotBot hardware version — sets `BOARD_DOTBOT_V<N>` |
| `BUILD_WITH_EKF` | BOOL | `OFF` | Enable EKF support (`DOBOT_CONTROL_LOOP_USE_EKF`) |
| `BUILD_WITH_PURE_PURSUIT` | BOOL | `OFF` | Enable Pure Pursuit support (`DOTBOT_CONTROL_LOOP_USE_PURE_PURSUIT`) |

Example enabling both optional features:

```bash
cmake -DDOTBOT_LIBS_DIR=<path> -DDOTBOT_VERSION=3 \
      -DBUILD_WITH_EKF=ON -DBUILD_WITH_PURE_PURSUIT=ON \
      -B build .
```

Alternatively, use the interactive TUI to configure all options:

```bash
ccmake -DDOTBOT_LIBS_DIR=<path> -B build .
```


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
