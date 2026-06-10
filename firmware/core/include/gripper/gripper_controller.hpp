#pragma once

#include "gripper/servo_bus.hpp"
#include "gripper/types.hpp"

namespace gripper {

class GripperController {
public:
    GripperController(ServoBus& bus, ControllerConfig config);

    bool initialize();
    bool enable();
    void disable();
    bool commandEffort(float left, float right);
    bool poll();
    void emergencyStop();
    bool clearFault();

    [[nodiscard]] const GripperState& state() const;

private:
    static float clamp(float value, float limit);
    bool setTorqueForBoth(bool enabled);
    void latchFault(FaultCode fault);

    ServoBus& bus_;
    ControllerConfig config_;
    GripperState state_{};
};

}  // namespace gripper
