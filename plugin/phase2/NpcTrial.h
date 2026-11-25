#pragma once

#include <chrono>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
class NpcTrial {
public:
    void Tick(UWorld* world, AShooterGameMode* gameMode);
private:
    std::chrono::steady_clock::time_point next_{};
    unsigned step_{};
};
}
