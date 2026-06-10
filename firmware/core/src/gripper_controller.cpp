#include "gripper/gripper_controller.hpp"

#include <algorithm>
#include <cmath>

namespace gripper {

GripperController::GripperController(ServoBus& bus, ControllerConfig config)
    : bus_(bus), config_(config) {
    config_.max_effort = std::clamp(std::abs(config_.max_effort), 0.0F, 1.0F);
}

bool GripperController::initialize() {
    disable();
    state_.initialized = false;

    if (!bus_.ping(config_.left_id) || !bus_.ping(config_.right_id)) {
        latchFault(FaultCode::kServoOffline);
        return false;
    }

    state_.fault = FaultCode::kNone;
    state_.initialized = true;
    return true;
}

bool GripperController::enable() {
    if (!state_.initialized || state_.fault != FaultCode::kNone) {
        return false;
    }
    if (!setTorqueForBoth(true)) {
        setTorqueForBoth(false);
        latchFault(FaultCode::kBusWriteFailed);
        return false;
    }
    state_.enabled = true;
    return true;
}

void GripperController::disable() {
    bus_.writeEffort(config_.left_id, 0.0F);
    bus_.writeEffort(config_.right_id, 0.0F);
    setTorqueForBoth(false);
    state_.enabled = false;
}

bool GripperController::commandEffort(float left, float right) {
    if (!state_.enabled || state_.fault != FaultCode::kNone) {
        return false;
    }

    const bool left_ok = bus_.writeEffort(config_.left_id, clamp(left, config_.max_effort));
    const bool right_ok = bus_.writeEffort(config_.right_id, clamp(right, config_.max_effort));
    if (!left_ok || !right_ok) {
        emergencyStop();
        state_.fault = FaultCode::kBusWriteFailed;
        return false;
    }
    return true;
}

bool GripperController::poll() {
    if (!state_.initialized) {
        return false;
    }

    ServoState left{};
    ServoState right{};
    if (!bus_.readState(config_.left_id, left) || !bus_.readState(config_.right_id, right)) {
        emergencyStop();
        state_.fault = FaultCode::kBusReadFailed;
        return false;
    }

    state_.left = left;
    state_.right = right;
    return true;
}

void GripperController::emergencyStop() {
    disable();
    state_.fault = FaultCode::kEmergencyStopped;
}

bool GripperController::clearFault() {
    if (state_.enabled) {
        return false;
    }
    state_.fault = FaultCode::kNone;
    return true;
}

const GripperState& GripperController::state() const {
    return state_;
}

float GripperController::clamp(float value, float limit) {
    return std::clamp(value, -limit, limit);
}

bool GripperController::setTorqueForBoth(bool enabled) {
    const bool left_ok = bus_.setTorqueEnabled(config_.left_id, enabled);
    const bool right_ok = bus_.setTorqueEnabled(config_.right_id, enabled);
    return left_ok && right_ok;
}

void GripperController::latchFault(FaultCode fault) {
    state_.enabled = false;
    state_.fault = fault;
}

}  // namespace gripper
