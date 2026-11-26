#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcTrial.h"
#include "Terrain.h"
#include "TrialSite.h"

#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>

namespace Phase2 {
namespace {
constexpr auto CharacterPath =
    L"/Human_NPCs_ASA/People/ZKs_Punch_Man_BP.ZKs_Punch_Man_BP_C";
constexpr auto ActorName = "AsaCivManagedNpcTrial";
constexpr double X = 107449.0;
constexpr double Y = 211985.0;
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

void RequestMove(APrimalCharacter* npc, const FVector& destination) {
    auto* controller = npc->ControllerField().Get();
    auto* aiClass = AAIController::StaticClass();
    if (!controller || !aiClass || !controller->ClassField()->IsChildOf(aiClass))
        throw std::runtime_error("NPC has no AI controller for movement");
    auto* function = controller->ClassField()->FindFunctionByName(FName("MoveToLocation"),
                                                                   EIncludeSuperFlag::IncludeSuper);
    alignas(16) std::byte parameters[128]{};
    if (!function || function->PropertiesSizeField() <= 0 ||
        function->PropertiesSizeField() > sizeof(parameters))
        throw std::runtime_error("reflected MoveToLocation unavailable or outside parameter bounds");

    const auto set = [&](const char* name, const wchar_t* value) {
        auto* property = function->FindPropertyByName(FName(name));
        if (!property || property->ArrayDimField() != 1 || property->Offset_InternalField() < 0 ||
            property->ElementSizeField() <= 0 ||
            property->Offset_InternalField() + property->ElementSizeField() > function->PropertiesSizeField() ||
            !property->ImportText_InContainer(value, parameters, controller, 0, nullptr))
            throw std::runtime_error("could not initialize reflected movement parameter");
    };
    const auto goal = fmt::format("(X={},Y={},Z={})", destination.X, destination.Y, destination.Z);
    const std::wstring text(goal.begin(), goal.end());
    set("Dest", text.c_str());
    set("AcceptanceRadius", L"80");
    set("bUsePathfinding", L"True");
    set("bAllowPartialPath", L"False");
    auto* result = function->FindPropertyByName(FName("ReturnValue"));
    if (!result || result->ElementSizeField() != 1 || result->Offset_InternalField() < 0 ||
        result->Offset_InternalField() >= function->PropertiesSizeField())
        throw std::runtime_error("unexpected reflected movement return value");
    controller->ProcessEvent(function, parameters);
    Log::GetLog()->info("NPC movement response={} goal=({},{},{})",
                        std::to_integer<unsigned>(parameters[result->Offset_InternalField()]),
                        destination.X, destination.Y, destination.Z);
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
        RequireTrial(world, gameMode, move_ ? L"?AltSaveDirectoryName=Phase2HumanNPCReflectedMove"
                                           : L"?AltSaveDirectoryName=Phase2HumanNPCController");
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
            if (move_) {
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
        if (move_ && DinoId(static_cast<APrimalDinoCharacter*>(npc)) != npcId_)
            throw std::runtime_error("managed NPC ID changed");
        if (step_ == 1) {
            if (move_ && !npc->ControllerField().Get()) {
                auto* dino = static_cast<APrimalDinoCharacter*>(npc);
                dino->bPreventStasis().Set(true);
                dino->Unstasis();
            }
            if (!npc->ControllerField().Get())
                InitializeController(npc);
            FVector position{};
            if (npc->GetActorLocation(&position))
                log->info("NPC trial initial position=({},{},{})", position.X, position.Y, position.Z);
            if (move_) {
                const auto goal = ObserveMoveGoal(world);
                goalX_ = goal.X;
                goalY_ = goal.Y;
                RequestMove(npc, goal);
            }
            ++step_;
            next_ = move_ ? now + 250ms : now + 12s;
            return;
        }
        FVector position{};
        if (move_ && movementSamples_ < 12) {
            ++movementSamples_;
            if (npc->GetActorLocation(&position)) {
                log->info("NPC movement sample={} horizontal_distance_cm={} position=({},{},{})", movementSamples_,
                            std::hypot(position.X - goalX_, position.Y - goalY_), position.X, position.Y, position.Z);
            }
            next_ = movementSamples_ == 12 ? now + 9s : now + 250ms;
            return;
        }
        if (npc->GetActorLocation(&position)) {
            log->info("NPC trial final position=({},{},{})", position.X, position.Y, position.Z);
            if (move_)
                log->info("NPC movement final horizontal distance_cm={}", std::hypot(position.X - goalX_, position.Y - goalY_));
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
