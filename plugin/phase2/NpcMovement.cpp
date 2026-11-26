#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcMovement.h"

#include <cstddef>
#include <stdexcept>

namespace Phase2 {
namespace {
AAIController* MovementController(APrimalCharacter* npc) {
    auto* controller = npc->ControllerField().Get();
    auto* aiClass = AAIController::StaticClass();
    if (!controller || !aiClass || !controller->ClassField()->IsChildOf(aiClass))
        throw std::runtime_error("NPC has no AI controller for movement");
    return static_cast<AAIController*>(controller);
}

}  // namespace

void StopMove(APrimalCharacter* npc) {
    auto* controller = MovementController(npc);
    auto* function = controller->ClassField()->FindFunctionByName(FName("StopMovement"),
                                                                   EIncludeSuperFlag::IncludeSuper);
    if (!function || function->PropertiesSizeField() != 0)
        throw std::runtime_error("reflected StopMovement unavailable or has parameters");
    controller->ProcessEvent(function, nullptr);
}

unsigned RequestMove(APrimalCharacter* npc, const FVector& destination, bool projectDestination) {
    auto* controller = MovementController(npc);
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
    if (projectDestination)
        set("bProjectDestinationToNavigation", L"True");
    auto* result = function->FindPropertyByName(FName("ReturnValue"));
    if (!result || result->ElementSizeField() != 1 || result->Offset_InternalField() < 0 ||
        result->Offset_InternalField() >= function->PropertiesSizeField())
        throw std::runtime_error("unexpected reflected movement return value");
    controller->ProcessEvent(function, parameters);
    return std::to_integer<unsigned>(parameters[result->Offset_InternalField()]);
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

void WakeForMovement(APrimalDinoCharacter* npc) {
    if (npc->ControllerField().Get())
        return;
    npc->bPreventStasis().Set(true);
    npc->Unstasis();
    if (!npc->ControllerField().Get())
        InitializeController(npc);
}

}  // namespace Phase2
