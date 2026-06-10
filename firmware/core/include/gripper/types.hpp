#pragma once

#include <cstdint>

namespace gripper {

enum class FaultCode : std::uint8_t {
    kNone = 0,
    kServoOffline,
    kBusWriteFailed,
    kBusReadFailed,
    kEmergencyStopped,
};

struct ServoState {
    std::int32_t position_ticks{0};
    std::int16_t velocity_raw{0};
    std::int16_t current_raw{0};
    std::uint8_t temperature_c{0};
};

struct GripperState {
    ServoState left{};
    ServoState right{};
    bool initialized{false};
    bool enabled{false};
    FaultCode fault{FaultCode::kNone};
};

struct ControllerConfig {
    std::uint8_t left_id{1};
    std::uint8_t right_id{2};
    float max_effort{0.25F};
};

}  // namespace gripper
