#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcPairTrial.h"
#include "NpcMovement.h"
#include "Terrain.h"
#include "TrialSite.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace Phase2 {
namespace {
constexpr std::array Names{"AsaCivNpcPairReachable", "AsaCivNpcPairUnreachable"};
constexpr std::array Offsets{-150.0, 150.0};
constexpr double StartX = TrialSiteX - 150.0;
constexpr double GoalX = TrialSiteX - 300.0;

std::array<APrimalDinoCharacter*, 2> FindActors(UWorld* world, UClass* type) {
    TArray<AActor*> all;
    UGameplayStatics::GetAllActorsOfClass(world, type, &all);
    std::array<APrimalDinoCharacter*, 2> actors{};
    const std::array names{FName(Names[0]), FName(Names[1])};
    for (auto* actor : all) {
        if (!actor || actor->ClassField() != type)
            continue;
        const auto entry = std::find(names.begin(), names.end(), actor->NameField());
        if (entry == names.end())
            continue;
        auto& found = actors[entry - names.begin()];
        FVector position{};
        if (found || !actor->GetActorLocation(&position) ||
            std::hypot(position.X - TrialSiteX, position.Y - TrialSiteY) > 1800.0)
            throw std::runtime_error("NPC pair name or trial bounds conflict");
        found = static_cast<APrimalDinoCharacter*>(actor);
    }
    return actors;
}
}

void NpcPairTrial::Tick(UWorld* world, AShooterGameMode* gameMode) {
    using namespace std::chrono_literals;
    constexpr unsigned Finished = 4;
    const auto now = std::chrono::steady_clock::now();
    if (stage_ == Finished || now < next_)
        return;
    if (next_ == std::chrono::steady_clock::time_point{}) {
        next_ = now + 35s;
        return;
    }
    const auto log = Log::GetLog();
    try {
        RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2HumanNPCReflectedMove");
        auto* type = TSoftClassPtr<APrimalDinoCharacter>(HumanNpcClassPath).LoadSynchronous();
        auto* base = APrimalDinoCharacter::StaticClass();
        if (!type || !base || !type->IsChildOf(base))
            throw std::runtime_error("NPC pair class is unavailable");
        const auto actors = FindActors(world, type);
        if (stage_ == 0 || stage_ == 3) {
            if (actors[0] || actors[1])
                throw std::runtime_error("unexpected managed NPC in trial site");
            if (stage_ == 3) {
                stage_ = Finished;
                log->info("NPC trial deletion verified count=0");
                return;
            }
            RequireEmptySite(world);
            goalGround_ = FoundationGroundZ(world, GoalX, TrialSiteY, 25.0, 25.0);
            std::array<double, 2> ground{};
            for (std::size_t i = 0; i < ground.size(); ++i)
                ground[i] = FoundationGroundZ(world, StartX, TrialSiteY + Offsets[i], 1.0, 1.0);
            for (std::size_t i = 0; i < actors.size(); ++i) {
                auto* actor = SpawnTrialActor(world, type, StartX, TrialSiteY + Offsets[i],
                                              ground[i] + 110.0, Names[i]);
                ids_[i] = DinoId(static_cast<APrimalDinoCharacter*>(actor));
                if (!ids_[i] || (i != 0 && ids_[i] == ids_[0]))
                    throw std::runtime_error("NPC pair has invalid or duplicate IDs");
            }
            closest_.fill(std::numeric_limits<double>::infinity());
            ++stage_;
            next_ = now + 3s;
            return;
        }
        for (std::size_t i = 0; i < actors.size(); ++i) {
            if (!actors[i] || DinoId(actors[i]) != ids_[i])
                throw std::runtime_error("NPC pair did not reconcile by ID");
        }
        if (stage_ == 1) {
            for (std::size_t i = 0; i < actors.size(); ++i) {
                WakeForMovement(actors[i]);
                const bool unreachable = i == 1;
                const FVector goal(GoalX, TrialSiteY, goalGround_ + (unreachable ? 10'000.0 : 0.0));
                const auto response = RequestMove(actors[i], goal, unreachable);
                log->info("NPC pair id={} unreachable={} response={}", ids_[i], unreachable, response);
            }
            ++stage_;
            next_ = now + 250ms;
            return;
        }
        for (std::size_t i = 0; i < actors.size(); ++i) {
            FVector position{};
            if (!actors[i]->GetActorLocation(&position))
                throw std::runtime_error("NPC pair position was not observed");
            closest_[i] = std::min(closest_[i], std::hypot(position.X - GoalX, position.Y - TrialSiteY));
        }
        next_ = now + 250ms;
        if (++samples_ < 24)
            return;
        for (std::size_t i = 0; i < actors.size(); ++i) {
            log->info("NPC pair id={} closest_horizontal_cm={}", ids_[i], closest_[i]);
            if (!actors[i]->Destroy(false, false))
                throw std::runtime_error("engine refused to remove managed NPC pair");
        }
        ++stage_;
        next_ = now + 2s;
    } catch (const std::exception& error) {
        stage_ = Finished;
        log->error("NPC trial stopped: {}", error.what());
    }
}
}
