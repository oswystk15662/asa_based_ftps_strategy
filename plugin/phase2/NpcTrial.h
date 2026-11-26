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
    void Tick(UWorld* world, AShooterGameMode* gameMode);
private:
    std::chrono::steady_clock::time_point next_{};
    unsigned step_{};
    std::optional<std::uint64_t> persistenceId_;
};
}
