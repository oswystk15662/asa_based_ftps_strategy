#pragma once
#include <string_view>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
void RunInventoryProbe(UWorld* world, AShooterGameMode* gameMode, std::string_view action,
                       unsigned expectedId);
int ObserveTrialWood(UWorld* world, AShooterGameMode* gameMode, unsigned expectedId);
}
