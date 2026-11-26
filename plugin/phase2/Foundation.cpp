#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "Foundation.h"
#include "TrialSite.h"

#include <stdexcept>

namespace Phase2 {
UClass* LoadFoundationClass() {
    return LoadStructureClass(L"/Game/PrimalEarth/CoreBlueprints/Items/Structures/Wooden/"
                              L"PrimalItemStructure_WoodFloor.PrimalItemStructure_WoodFloor_C");
}

void RunFoundationProbe(UWorld* world, AShooterGameMode* gameMode, std::string_view action,
                        unsigned expectedId) {
    RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2FoundationPlacement");
    auto* foundationClass = LoadFoundationClass();
    auto nearby = NearbyStructures(world);
    const auto log = Log::GetLog();
    if (action == "verify-empty") {
        if (!nearby.empty() || expectedId)
            throw std::runtime_error("trial cell is occupied or an ID was supplied");
        RequireEmptySite(world);
        log->info("Foundation site verified empty count=0");
        return;
    }
    if (action == "verify" || action == "remove") {
        if (nearby.size() != 1 || nearby.front()->ClassField() != foundationClass ||
            !expectedId || nearby.front()->StructureIDField() != expectedId)
            throw std::runtime_error("managed foundation ID and site did not reconcile");
        if (action == "verify") {
            auto* actor = nearby.front();
            log->info("Foundation verified id={} count=1 health={} max_health={} owner_player={}",
                      expectedId, actor->HealthField(), actor->MaxHealthField(), actor->OwningPlayerIDField());
            return;
        }
        if (!nearby.front()->Destroy(false, false))
            throw std::runtime_error("engine refused to destroy the managed foundation");
        gameMode->SaveWorld(true, false, false);
        log->info("Foundation destroyed and save requested id={}", expectedId);
        return;
    }
    if ((action != "place" && action != "place-unsaved") || expectedId)
        throw std::runtime_error("unknown placement probe action or unexpected ID");
    auto* actor = SpawnAtTrial(world, foundationClass);
    const auto id = actor->StructureIDField();
    nearby = NearbyStructures(world);
    if (!id || nearby.size() != 1 || nearby.front() != actor)
        throw std::runtime_error("spawned foundation did not reconcile uniquely");
    if (action == "place-unsaved") {
        log->info("Foundation placed without save id={} count=1", id);
        return;
    }
    gameMode->SaveWorld(true, false, false);
    log->info("Foundation placed and save requested id={} count=1 health={} max_health={} owner_player={}",
              id, actor->HealthField(), actor->MaxHealthField(), actor->OwningPlayerIDField());
}
}  // namespace Phase2
