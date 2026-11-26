#pragma once

#include <chrono>
#include <cstdint>
#include <optional>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
class NpcTrial {
public:
    enum class Movement { None, Observe, StopAtGoal, Unreachable, Unprojected };
    explicit NpcTrial(std::optional<std::uint64_t> persistenceId = {}) : persistenceId_(persistenceId) {}
    explicit NpcTrial(Movement movement) : movement_(movement) {}
    void Tick(UWorld* world, AShooterGameMode* gameMode);
private:
    std::chrono::steady_clock::time_point next_{};
    unsigned step_{};
    std::optional<std::uint64_t> persistenceId_;
    Movement movement_{};
    std::uint64_t npcId_{};
    unsigned movementSamples_{};
    bool stopIssued_{};
    double maxDistanceAfterStop_{};
    double goalX_{};
    double goalY_{};
    double goalZ_{};
};
}
