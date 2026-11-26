#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcTrial.h"
#include "Terrain.h"
#include "TrialSite.h"

#include <cmath>
#include <stdexcept>

namespace Phase2 {
namespace {
constexpr auto CharacterPath =
    L"/Human_NPCs_ASA/People/ZKs_Punch_Man_BP.ZKs_Punch_Man_BP_C";
constexpr auto ActorName = "AsaCivManagedNpcTrial";
constexpr double X = 107449.0;
constexpr double Y = 211985.0;

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

void InitializeController(APrimalCharacter* npc) {
    auto* aiType = AAIController::StaticClass();
    auto* configured = npc->AIControllerClassField().uClass;
    if (!aiType || !configured || !configured->IsChildOf(aiType)) {
        Log::GetLog()->warn("NPC trial has no default AI controller class");
        return;
    }
    auto* type = npc->ClassField();
    if (auto* dino = APrimalDinoCharacter::StaticClass(); dino && type->IsChildOf(dino))
        static_cast<APrimalDinoCharacter*>(npc)->SpawnDefaultController();
    else if (auto* survivor = AShooterCharacter::StaticClass(); survivor && type->IsChildOf(survivor))
        static_cast<AShooterCharacter*>(npc)->SpawnDefaultController();
    else
        npc->SpawnDefaultController();
    Log::GetLog()->info("NPC trial explicit controller initialization attached={}",
                        npc->ControllerField().Get() != nullptr);
}

std::uint64_t DinoId(APrimalDinoCharacter* npc) {
    return (std::uint64_t{npc->DinoID1Field()} << 32) | npc->DinoID2Field();
}

void ProbePersistence(UWorld* world, AShooterGameMode* gameMode, std::uint64_t expectedId) {
    RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2HumanNPCPersistence");
    auto* type = TSoftClassPtr<APrimalDinoCharacter>(CharacterPath).LoadSynchronous();
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
    try {
        if (persistenceId_) {
            ProbePersistence(world, gameMode, *persistenceId_);
            step_ = Finished;
            return;
        }
        RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2HumanNPCController");
        auto* type = TSoftClassPtr<APrimalCharacter>(CharacterPath).LoadSynchronous();
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
        if (step_ == 1) {
            if (!npc->ControllerField().Get())
                InitializeController(npc);
            FVector position{};
            if (npc->GetActorLocation(&position))
                log->info("NPC trial initial position=({},{},{})", position.X, position.Y, position.Z);
            ++step_;
            next_ = now + 12s;
            return;
        }
        FVector position{};
        if (npc->GetActorLocation(&position))
            log->info("NPC trial final position=({},{},{})", position.X, position.Y, position.Z);
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
