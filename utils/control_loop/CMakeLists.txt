cmake_minimum_required(VERSION 3.10)
project(dotbot_control_loop VERSION 1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release)

# Set default dotbot version
if(NOT DEFINED DOTBOT_VERSION)
    set(DOTBOT_VERSION 3)
endif()

# Require DOTBOT_LIBS_DIR
if(NOT DEFINED DOTBOT_LIBS_DIR)
    message(FATAL_ERROR "DOTBOT_LIBS_DIR must be set")
endif()

# Create shared library
add_library(${PROJECT_NAME} SHARED
    ${DOTBOT_LIBS_DIR}/drv/control_loop/control_loop.c
)

# Set include directories
target_include_directories(${PROJECT_NAME} PRIVATE
    ${DOTBOT_LIBS_DIR}/drv
)

# Set preprocessor definitions
target_compile_definitions(${PROJECT_NAME} PRIVATE
    BOARD_DOTBOT_V${DOTBOT_VERSION}
    DOTBOT_SIMULATION
)

# Add fast-math flag
target_compile_options(${PROJECT_NAME} PRIVATE -ffast-math)
