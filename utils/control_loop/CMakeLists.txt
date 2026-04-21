cmake_minimum_required(VERSION 3.10)
project(dotbot_control_loop VERSION 1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release)

set(DOTBOT_VERSION "3" CACHE STRING "DotBot hardware version")
set(BUILD_WITH_EKF OFF CACHE BOOL "Enable EKF support in the control loop")
set(BUILD_WITH_PURE_PURSUIT OFF CACHE BOOL "Enable Pure Pursuit support in the control loop")

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

if(BUILD_WITH_EKF)
    target_compile_definitions(${PROJECT_NAME} PRIVATE DOTBOT_CONTROL_LOOP_USE_EKF)
endif()

if(BUILD_WITH_PURE_PURSUIT)
    target_compile_definitions(${PROJECT_NAME} PRIVATE DOTBOT_CONTROL_LOOP_USE_PURE_PURSUIT)
endif()

# Add fast-math flag
target_compile_options(${PROJECT_NAME} PRIVATE -ffast-math)
