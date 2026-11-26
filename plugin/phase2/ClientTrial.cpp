#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "ClientTrial.h"
#include "TrialSite.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace Phase2 {
void LogClientTrial(UWorld* world, AShooterGameMode* gameMode) {
    RequireTrialWorld(gameMode, L"?AltSaveDirectoryName=Phase2ClientVerification");
    unsigned players = 0;
    double nearest = std::numeric_limits<double>::infinity();
    for (auto& entry : world->PlayerControllerListField()) {
        const auto controller = entry.Get();
        if (!controller)
            continue;
        ++players;
        auto* character = controller->CharacterField().Get();
        FVector location{};
        if (character && character->GetActorLocation(&location))
            nearest = std::min(nearest, std::hypot(location.X - TrialSiteX, location.Y - TrialSiteY));
    }
    const auto structures = NearbyStructures(world);
    const auto log = Log::GetLog();
    log->info("Client trial players={} nearest_xy_cm={} nearby_structures={}", players,
              std::isfinite(nearest) ? std::to_string(nearest) : "unobserved",
              structures.size());
    constexpr std::size_t MaxReported = 8;
    for (std::size_t i = 0; i < std::min(MaxReported, structures.size()); ++i) {
        auto* actor = structures[i];
        log->info("Client trial structure id={} class={} health={} max_health={} player_owned={}",
                  actor->StructureIDField(), actor->ClassField()->NameField().ToString().ToStringUTF8(),
                  actor->HealthField(), actor->MaxHealthField(), actor->OwningPlayerIDField() != 0);
    }
}
}
