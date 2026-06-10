#include <cassert>
#include <cmath>
#include <cstdint>
#include <unordered_map>

#include "gripper/gripper_controller.hpp"

namespace {

class FakeServoBus final : public gripper::ServoBus {
public:
    bool online{true};
    bool writes_succeed{true};
    bool reads_succeed{true};
    std::unordered_map<std::uint8_t, float> efforts;

    bool ping(std::uint8_t) override { return online; }
    bool setTorqueEnabled(std::uint8_t, bool) override { return writes_succeed; }
    bool writeEffort(std::uint8_t id, float effort) override {
        efforts[id] = effort;
        return writes_succeed;
    }
    bool readState(std::uint8_t id, gripper::ServoState& state) override {
        state.position_ticks = static_cast<std::int32_t>(id) * 100;
        return reads_succeed;
    }
};

void testInitializationRejectsOfflineServo() {
    FakeServoBus bus;
    bus.online = false;
    gripper::GripperController controller(bus, {});

    assert(!controller.initialize());
    assert(controller.state().fault == gripper::FaultCode::kServoOffline);
}

void testEffortIsClamped() {
    FakeServoBus bus;
    gripper::ControllerConfig config{};
    config.max_effort = 0.2F;
    gripper::GripperController controller(bus, config);

    assert(controller.initialize());
    assert(controller.enable());
    assert(controller.commandEffort(0.8F, -0.7F));
    assert(std::abs(bus.efforts[1] - 0.2F) < 0.0001F);
    assert(std::abs(bus.efforts[2] + 0.2F) < 0.0001F);
}

void testReadFailureStopsController() {
    FakeServoBus bus;
    gripper::GripperController controller(bus, {});

    assert(controller.initialize());
    assert(controller.enable());
    bus.reads_succeed = false;
    assert(!controller.poll());
    assert(!controller.state().enabled);
    assert(controller.state().fault == gripper::FaultCode::kBusReadFailed);
}

}  // namespace

int main() {
    testInitializationRejectsOfflineServo();
    testEffortIsClamped();
    testReadFailureStopsController();
    return 0;
}
