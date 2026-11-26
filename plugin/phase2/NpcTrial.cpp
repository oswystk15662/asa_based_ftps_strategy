#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcMovement.h"
#include "NpcTrial.h"
#include "Terrain.h"
#include "TrialSite.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace Phase2 {
namespace {
constexpr auto ActorName = "AsaCivManagedNpcTrial";
constexpr double X = TrialSiteX;
constexpr double Y = TrialSiteY;
constexpr double MoveDistance = 300.0;

FVector ObserveMoveGoal(UWorld* world) {
    const std::array candidates{FVector(X - MoveDistance, Y, 0), FVector(X, Y - MoveDistance, 0),
                                FVector(X, Y + MoveDistance, 0), FVector(X + MoveDistance, Y, 0)};
    for (auto goal : candidates) {
        try {
            goal.Z = FoundationGroundZ(world, goal.X, goal.Y, 25.0, 25.0);
            return goal;
        } catch (const std::runtime_error& error) {
            Log::GetLog()->info("NPC movement candidate rejected x={} y={} reason={}", goal.X, goal.Y, error.what());
        }
    }
    throw std::runtime_error("no observed dry movement goal in trial bounds");
}


APrimalCharacter* FindManagedNpc(UWorld* world, UClass* type) {
    TArray<AActor*> actors;
    UGameplayStatics::GetAllActorsOfClass(world, type, &actors);
    APrimalCharacter* match = nullptr;
    const FName name(ActorName);
    for (auto* actor : actors) {
        if (!actor || actor->ClassField() != type || actor->NameField() != name)
            continue;
        FVector location{};
        if (match || !actor->GetActorLocation(&location) ||
            std::abs(location.X - X) > 1500 || std::abs(location.Y - Y) > 1500)
            throw std::runtime_error("managed NPC identity or trial bounds conflict");
        match = static_cast<APrimalCharacter*>(actor);
    }
    return match;
}

void ProbePersistence(UWorld* world, AShooterGameMode* gameMode, std::uint64_t expectedId) {
    RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2HumanNPCPersistence");
    auto* type = TSoftClassPtr<APrimalDinoCharacter>(HumanNpcClassPath).LoadSynchronous();
    auto* base = APrimalDinoCharacter::StaticClass();
    if (!type || !base || !type->IsChildOf(base))
        throw std::runtime_error("NPC class does not support dino IDs");

    if (!expectedId) {
        if (FindManagedNpc(world, type))
            throw std::runtime_error("managed NPC already present");
        RequireEmptySite(world);
        const auto ground = FoundationGroundZ(world, X, Y, 150.0, 150.0);
        auto* actor = SpawnTrialActor(world, type, X, Y, ground + 110.0, ActorName);
        if (FindManagedNpc(world, type) != actor)
            throw std::runtime_error("NPC persistence spawn did not reconcile");
        const auto id = DinoId(static_cast<APrimalDinoCharacter*>(actor));
        if (!id)
            throw std::runtime_error("managed NPC has no nonzero dino ID");
        gameMode->SaveWorld(true, false, false);
        Log::GetLog()->info("NPC persistence saved id={}", id);
        return;
    }

    TArray<AActor*> actors;
    UGameplayStatics::GetAllActorsOfClass(world, type, &actors);
    unsigned matches = 0;
    bool inTrialSite = false;
    for (auto* actor : actors) {
        if (!actor || actor->ClassField() != type ||
            DinoId(static_cast<APrimalDinoCharacter*>(actor)) != expectedId)
            continue;
        ++matches;
        FVector location{};
        inTrialSite = actor->GetActorLocation(&location) &&
            std::abs(location.X - X) <= 1500 && std::abs(location.Y - Y) <= 1500;
    }
    Log::GetLog()->info("NPC persistence verified id={} loaded_class_count={} matches={} in_trial_site={}",
                        expectedId, actors.Num(), matches, matches == 1 && inTrialSite);
}
}  // namespace

void NpcTrial::Tick(UWorld* world, AShooterGameMode* gameMode) {
    using namespace std::chrono_literals;
    constexpr unsigned Finished = 4;
    if (step_ == Finished)
        return;
    const auto now = std::chrono::steady_clock::now();
    if (next_ == std::chrono::steady_clock::time_point{}) {
        next_ = now + 35s;
        return;
    }
    if (now < next_)
        return;

    const auto log = Log::GetLog();
    const bool move = movement_ != Movement::None;
    try {
        if (persistenceId_) {
            ProbePersistence(world, gameMode, *persistenceId_);
            step_ = Finished;
            return;
        }
        RequireTrial(world, gameMode, move ? L"?AltSaveDirectoryName=Phase2HumanNPCReflectedMove"
                                          : L"?AltSaveDirectoryName=Phase2HumanNPCController");
        auto* type = TSoftClassPtr<APrimalCharacter>(HumanNpcClassPath).LoadSynchronous();
        if (!type)
            throw std::runtime_error("NPC character class unavailable");
        auto* npc = FindManagedNpc(world, type);
        if (step_ == 0) {
            if (npc)
                throw std::runtime_error("managed NPC already present");
            const auto ground = FoundationGroundZ(world, X, Y, 150.0, 150.0);
            auto* actor = SpawnTrialActor(world, type, X, Y, ground + 110.0, ActorName);
            if (FindManagedNpc(world, type) != actor)
                throw std::runtime_error("spawn did not reconcile with the managed name");
            if (move) {
                auto* base = APrimalDinoCharacter::StaticClass();
                if (!base || !type->IsChildOf(base))
                    throw std::runtime_error("movement requires an ASA dino pawn");
                npcId_ = DinoId(static_cast<APrimalDinoCharacter*>(actor));
                if (!npcId_)
                    throw std::runtime_error("movement requires a nonzero NPC ID");
            }
            log->info("NPC trial spawned name={}", ActorName);
            ++step_;
            next_ = now + 3s;
            return;
        }
        if (step_ == 3) {
            if (npc)
                throw std::runtime_error("managed NPC still present after deletion");
            step_ = Finished;
            log->info("NPC trial deletion verified count=0");
            return;
        }
        if (!npc)
            throw std::runtime_error("managed NPC is unobserved");
        if (move && DinoId(static_cast<APrimalDinoCharacter*>(npc)) != npcId_)
            throw std::runtime_error("managed NPC ID changed");
        if (step_ == 1) {
            if (move)
                WakeForMovement(static_cast<APrimalDinoCharacter*>(npc));
            else if (!npc->ControllerField().Get())
                InitializeController(npc);
            FVector position{};
            if (npc->GetActorLocation(&position))
                log->info("NPC trial initial position=({},{},{})", position.X, position.Y, position.Z);
            if (move) {
                auto goal = ObserveMoveGoal(world);
                const bool projectDestination = movement_ == Movement::Unreachable;
                if (projectDestination || movement_ == Movement::Unprojected)
                    goal.Z += 10'000.0;
                goalX_ = goal.X;
                goalY_ = goal.Y;
                goalZ_ = goal.Z;
                const auto response = RequestMove(npc, goal, projectDestination);
                log->info("NPC movement response={} goal=({},{},{})", response, goal.X, goal.Y, goal.Z);
            }
            ++step_;
            next_ = move ? now + 250ms : now + 12s;
            return;
        }
        FVector position{};
        const unsigned samples = movement_ == Movement::StopAtGoal ? 48 : 12;
        if (move && movementSamples_ < samples) {
            ++movementSamples_;
            if (npc->GetActorLocation(&position)) {
                const auto distance = std::hypot(position.X - goalX_, position.Y - goalY_);
                if (movement_ == Movement::StopAtGoal && !stopIssued_ && distance <= 80.0) {
                    log->info("NPC movement stop requested sample={} distance_cm={}", movementSamples_, distance);
                    StopMove(npc);
                    stopIssued_ = true;
                    log->info("NPC movement stop returned sample={}", movementSamples_);
                }
                if (stopIssued_)
                    maxDistanceAfterStop_ = std::max(maxDistanceAfterStop_, distance);
                log->info("NPC movement sample={} horizontal_distance_cm={} position=({},{},{})", movementSamples_,
                            distance, position.X, position.Y, position.Z);
            }
            next_ = movementSamples_ == samples && movement_ != Movement::StopAtGoal ? now + 9s : now + 250ms;
            return;
        }
        if (npc->GetActorLocation(&position)) {
            log->info("NPC trial final position=({},{},{})", position.X, position.Y, position.Z);
            if (move) {
                const auto distance = std::hypot(position.X - goalX_, position.Y - goalY_);
                log->info("NPC movement final horizontal distance_cm={} vertical_distance_cm={}",
                          distance, std::abs(position.Z - goalZ_));
                if (movement_ == Movement::StopAtGoal)
                    log->info("NPC movement stop observed issued={} max_distance_after_stop_cm={}", stopIssued_,
                              stopIssued_ ? std::max(maxDistanceAfterStop_, distance) : 0.0);
            }
        }
        if (!npc->Destroy(false, false))
            throw std::runtime_error("engine refused to remove managed NPC");
        ++step_;
        next_ = now + 2s;
    } catch (const std::exception& error) {
        step_ = Finished;
        log->error("NPC trial stopped: {}", error.what());
    }
}
}  // namespace Phase2
