cmake_minimum_required(VERSION 3.24)

project(lh2)


if (MSVC)
    set(CMAKE_BUILD_TYPE Release)
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
else()
    add_compile_options(-std=c11 -Ofast -Wall -Werror)
endif()

add_library(lh2 SHARED lh2.c)
set_target_properties(lh2 PROPERTIES PREFIX "")

install(TARGETS lh2 DESTINATION ${CMAKE_CURRENT_SOURCE_DIR})
