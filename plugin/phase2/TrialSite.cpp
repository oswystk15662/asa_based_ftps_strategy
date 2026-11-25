#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "TrialSite.h"
#include "Terrain.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace Phase2 {
namespace {
constexpr double SiteX = 107449.0;
constexpr double SiteY = 211985.0;
constexpr double SiteZ = -14421.93;

bool HasSaveOption(std::wstring_view option) {
    const std::wstring_view commandLine(GetCommandLineW());
    const auto start = commandLine.find(option);
    if (start == std::wstring_view::npos)
        return false;
    const auto end = start + option.size();
    return end == commandLine.size() || std::wstring_view(L" ?\"").find(commandLine[end]) != std::wstring_view::npos;
}

}  // namespace

std::vector<APrimalStructure*> NearbyStructures(UWorld* world) {
    auto* type = APrimalStructure::StaticClass();
    if (!type)
        throw std::runtime_error("structure class unavailable");
    TArray<AActor*> actors;
    UGameplayStatics::GetAllActorsOfClass(world, type, &actors);
    std::vector<APrimalStructure*> nearby;
    for (auto* actor : actors) {
        FVector position{};
        if (!actor || !actor->GetActorLocation(&position))
            continue;
        if (std::abs(position.X - SiteX) <= 600.0 && std::abs(position.Y - SiteY) <= 600.0 &&
            std::abs(position.Z - SiteZ) <= 1000.0)
            nearby.push_back(static_cast<APrimalStructure*>(actor));
    }
    return nearby;
}

void RequireTrial(UWorld* world, AShooterGameMode* gameMode, std::wstring_view saveOption) {
    FString map;
    gameMode->GetMapName(&map);
    if (!HasSaveOption(saveOption) || map.ToStringUTF8() != "TheIsland_WP" ||
        world->PlayerControllerListField().Num() != 0)
        throw std::runtime_error("requires the isolated The Island trial save with no players");
}

UClass* LoadStructureClass(const wchar_t* itemPath) {
    auto* itemClass = TSoftClassPtr<UPrimalItem>(itemPath).LoadSynchronous();
    if (!itemClass)
        throw std::runtime_error("structure item class unavailable");
    auto* item = static_cast<UPrimalItem*>(itemClass->GetDefaultObject(false));
    if (!item)
        throw std::runtime_error("structure item defaults unavailable");
    const auto& reference = item->StructureToBuildField();
    auto* structureClass = reference.LoadSynchronous();
    if (!structureClass)
        throw std::runtime_error("item structure class unavailable");
    FString structurePath;
    auto path = reference.ToSoftObjectPath();
    path.ToString(&structurePath);
    Log::GetLog()->info("Trial structure resolved: {}", structurePath.ToStringUTF8());
    return structureClass;
}

void RequireEmptySite(UWorld* world) {
    if (!NearbyStructures(world).empty())
        throw std::runtime_error("trial cell already occupied");
    FoundationGroundZ(world, SiteX, SiteY, 150.0, 150.0);
}

APrimalStructure* SpawnAtTrial(UWorld* world, UClass* type) {
    if (!NearbyStructures(world).empty())
        throw std::runtime_error("trial cell already occupied");
    auto* defaults = static_cast<APrimalStructure*>(type->GetDefaultObject(false));
    if (!defaults)
        throw std::runtime_error("structure class defaults unavailable");
    const auto extent = defaults->PlacementEncroachmentBoxExtentField();
    const auto offset = defaults->PlacementHitLocOffsetField();
    if (!std::isfinite(extent.X) || !std::isfinite(extent.Y) || std::abs(extent.X) > 400 ||
        std::abs(extent.Y) > 400 || !std::isfinite(offset.Z) || std::abs(offset.Z) > 250)
        throw std::runtime_error("structure placement geometry is outside the trial bounds");
    const auto ground = FoundationGroundZ(world, SiteX, SiteY, std::max(150.0, std::abs(extent.X)),
                                         std::max(150.0, std::abs(extent.Y)));
    if (std::abs(ground - SiteZ) > 5.0)
        throw std::runtime_error("trial cell elevation changed");
    Log::GetLog()->info("Trial site passed: location=({},{},{}) extent=({},{})", SiteX, SiteY,
                        ground + offset.Z, extent.X, extent.Y);
    return static_cast<APrimalStructure*>(SpawnTrialActor(world, type, SiteX, SiteY, ground + offset.Z));
}

AActor* SpawnTrialActor(UWorld* world, UClass* type, double x, double y, double z, const char* name) {
    const FVector location(x, y, z);
    const FRotator rotation(0, 0, 0);
    FActorSpawnParameters options;
    if (name) {
        options.Name = FName(name);
        options.NameMode = FActorSpawnParameters::Required_ReturnNull;
    }
    options.SpawnCollisionHandlingOverride[0] =
        static_cast<unsigned char>(ESpawnActorCollisionHandlingMethod::DontSpawnIfColliding);
    options.bRemoteOwned = options.bNoFail = options.bDeferConstruction = options.bWillStasisAfterSpawn = false;
    options.bDeferBeginPlay = options.bAllowDuringConstructionScript = false;
    options.ExtraSpawnData = 0;
    auto* actor = world->SpawnActor(type, &location, &rotation, options);
    if (!actor)
        throw std::runtime_error("engine refused collision-safe spawn at trial cell");
    return actor;
}
}  // namespace Phase2
