#pragma once

#include <array>
#include <chrono>
#include <cstdint>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
class NpcPairTrial {
public:
    void Tick(UWorld* world, AShooterGameMode* gameMode);

private:
    std::chrono::steady_clock::time_point next_{};
    unsigned stage_{};
    unsigned samples_{};
    std::array<std::uint64_t, 2> ids_{};
    std::array<double, 2> closest_{};
    double goalGround_{};
};
}
