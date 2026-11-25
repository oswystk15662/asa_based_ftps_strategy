#pragma once

#include <chrono>

struct AShooterGameMode;
struct UWorld;

namespace Phase2 {
class NpcSurvey {
public:
    void Tick(UWorld* world, AShooterGameMode* gameMode);

private:
    std::chrono::steady_clock::time_point started_{};
    unsigned sample_{};
};
}
