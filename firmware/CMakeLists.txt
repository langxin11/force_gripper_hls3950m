cmake_minimum_required(VERSION 3.20)
project(hls3950_gripper_firmware LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(gripper_core
    core/src/gripper_controller.cpp
)
target_include_directories(gripper_core PUBLIC core/include)
target_compile_options(gripper_core PRIVATE -Wall -Wextra -Wpedantic -Werror)

enable_testing()
add_executable(gripper_core_tests tests/test_gripper_controller.cpp)
target_link_libraries(gripper_core_tests PRIVATE gripper_core)
target_compile_options(gripper_core_tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME gripper_core_tests COMMAND gripper_core_tests)
