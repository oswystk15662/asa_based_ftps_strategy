#pragma once

#include <chrono>
#include <cstdint>
#include <optional>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
class NpcTrial {
public:
    explicit NpcTrial(std::optional<std::uint64_t> persistenceId = {}) : persistenceId_(persistenceId) {}
    explicit NpcTrial(bool move) : move_(move) {}
    void Tick(UWorld* world, AShooterGameMode* gameMode);
private:
    std::chrono::steady_clock::time_point next_{};
    unsigned step_{};
    std::optional<std::uint64_t> persistenceId_;
    bool move_{};
    std::uint64_t npcId_{};
    unsigned movementSamples_{};
    double goalX_{};
    double goalY_{};
};
}
