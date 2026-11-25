#pragma once
#include <string_view>
#include <vector>

struct UWorld;
struct UClass;
struct AShooterGameMode;
struct APrimalStructure;
struct AActor;

namespace Phase2 {
inline constexpr double TrialSiteX = 107449.0;
inline constexpr double TrialSiteY = 211985.0;
void RequireTrialWorld(AShooterGameMode* gameMode, std::wstring_view saveOption);
void RequireTrial(UWorld* world, AShooterGameMode* gameMode, std::wstring_view saveOption);
void RequireEmptySite(UWorld* world);
std::vector<APrimalStructure*> NearbyStructures(UWorld* world);
UClass* LoadStructureClass(const wchar_t* itemPath);
APrimalStructure* SpawnAtTrial(UWorld* world, UClass* type);
AActor* SpawnTrialActor(UWorld* world, UClass* type, double x, double y, double z,
                        const char* name = nullptr);
}
