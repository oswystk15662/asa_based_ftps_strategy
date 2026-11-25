#pragma once

#include <string_view>

struct AShooterGameMode;
struct UClass;
struct UWorld;

namespace Phase2 {
UClass* LoadFoundationClass();
void RunFoundationProbe(UWorld* world, AShooterGameMode* gameMode, std::string_view action,
                        unsigned expectedId);
}
