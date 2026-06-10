#pragma once

#include <cstdint>

#include "gripper/types.hpp"

namespace gripper {

class ServoBus {
public:
    virtual ~ServoBus() = default;

    virtual bool ping(std::uint8_t id) = 0;
    virtual bool setTorqueEnabled(std::uint8_t id, bool enabled) = 0;
    virtual bool writeEffort(std::uint8_t id, float normalized_effort) = 0;
    virtual bool readState(std::uint8_t id, ServoState& state) = 0;
};

}  // namespace gripper
