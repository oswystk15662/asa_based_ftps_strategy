#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "Inventory.h"
#include "TrialSite.h"

#include <exception>
#include <stdexcept>
#include <vector>

namespace Phase2 {
namespace {
constexpr auto BoxItem = L"/Game/PrimalEarth/CoreBlueprints/Items/Structures/Misc/"
                         L"PrimalItemStructure_StorageBox_Small.PrimalItemStructure_StorageBox_Small_C";
constexpr auto BoxClass = L"/Game/PrimalEarth/Structures/StorageBox_Small.StorageBox_Small_C";
constexpr auto WoodItem = L"/Game/PrimalEarth/CoreBlueprints/Resources/"
                          L"PrimalItemResource_Wood.PrimalItemResource_Wood_C";

UPrimalItem* OnlyWoodStack(UPrimalInventoryComponent* inventory, UClass* wood, int quantity) {
    auto& items = inventory->InventoryItemsField();
    if (quantity == 0 && items.Num() == 0)
        return nullptr;
    if (quantity <= 0 || items.Num() != 1 || !items[0] || items[0]->ClassField() != wood ||
        items[0]->GetItemQuantity() != quantity)
        throw std::runtime_error("inventory precondition failed: unexpected item or quantity");
    return items[0];
}

APrimalStructureItemContainer* FindTrialBox(UWorld* world, UClass* boxClass, unsigned expectedId) {
    const auto nearby = NearbyStructures(world);
    if (!boxClass || !expectedId || nearby.size() != 1 || nearby.front()->ClassField() != boxClass ||
        nearby.front()->StructureIDField() != expectedId)
        throw std::runtime_error("managed inventory structure ID and site did not reconcile");
    return static_cast<APrimalStructureItemContainer*>(nearby.front());
}

UPrimalItem* AddWood(UWorld* world, UPrimalInventoryComponent* inventory, UClass* wood,
                     int quantity, bool separateStack) {
    return UPrimalItem::AddNewItem(wood, inventory, false, separateStack, 0.f, true, quantity,
        false, 0.f, false, {}, 0.f, false, false, false, false, true, false, world);
}

void ProbeCapacity(UWorld* world, UPrimalInventoryComponent* inventory, UClass* wood, unsigned id) {
    OnlyWoodStack(inventory, wood, 0);
    const auto limit = inventory->GetMaxInventoryItems(false);
    if (limit <= 0 || limit > 24)
        throw std::runtime_error("capacity outside the bounded trial range");
    auto& items = inventory->InventoryItemsField();
    std::vector<FItemNetID> inserted;
    inserted.reserve(limit);
    bool extraAllowed = false;
    bool atLimit = false;
    std::exception_ptr failure;
    try {
        for (int i = 0; i < limit; ++i) {
            auto* item = AddWood(world, inventory, wood, 1, true);
            if (!item)
                throw std::runtime_error("engine refused a slot before the reported capacity");
            inserted.push_back(item->ItemIDField());
            if (items.Num() != i + 1 || item->GetItemQuantity() != 1)
                throw std::runtime_error("unexpected trial stack count or quantity");
        }
        atLimit = inventory->IsAtMaxInventoryItems();
        // Use a different item class to test the limit without merging into a wood stack.
        constexpr auto stonePath = L"/Game/PrimalEarth/CoreBlueprints/Resources/"
                                   L"PrimalItemResource_Stone.PrimalItemResource_Stone_C";
        auto* stone = TSoftClassPtr<UPrimalItem>(stonePath).LoadSynchronous();
        auto* stoneDefaults = stone ? static_cast<UPrimalItem*>(stone->GetDefaultObject(false)) : nullptr;
        if (!stoneDefaults)
            throw std::runtime_error("stone class defaults unavailable");
        int extraQuantity = 1;
        extraAllowed = inventory->AllowAddInventoryItem(stoneDefaults, &extraQuantity, true, true);
    } catch (...) {
        failure = std::current_exception();
    }
    for (const auto& itemId : inserted) {
        if (!inventory->RemoveItem(&itemId, false, false, false, false))
            throw std::runtime_error("capacity trial cleanup failed");
    }
    OnlyWoodStack(inventory, wood, 0);
    if (failure)
        std::rethrow_exception(failure);
    Log::GetLog()->info("Inventory trial capacity id={} slots={} at_limit={} extra_type_allowed={} wood_after=0",
                        id, limit, atLimit, extraAllowed);
}
}  // namespace

void RunInventoryProbe(UWorld* world, AShooterGameMode* gameMode, std::string_view action,
                       unsigned expectedId) {
    RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2Inventory");
    auto* boxClass = LoadStructureClass(BoxItem);
    auto* container = APrimalStructureItemContainer::StaticClass();
    if (!container || !boxClass->IsChildOf(container))
        throw std::runtime_error("resolved structure is not an inventory container");
    const auto log = Log::GetLog();
    if (action == "create") {
        if (expectedId)
            throw std::runtime_error("unexpected existing ID for create");
        auto* box = SpawnAtTrial(world, boxClass);
        const auto id = box->StructureIDField();
        const auto nearby = NearbyStructures(world);
        if (!id || nearby.size() != 1 || nearby.front() != box)
            throw std::runtime_error("trial box did not reconcile uniquely");
        gameMode->SaveWorld(true, false, false);
        log->info("Inventory trial created id={} owner_player={}", id, box->OwningPlayerIDField());
        return;
    }

    auto* box = FindTrialBox(world, boxClass, expectedId);
    auto* inventory = box->MyInventoryComponentField();
    auto* wood = TSoftClassPtr<UPrimalItem>(WoodItem).LoadSynchronous();
    if (!inventory || !wood)
        throw std::runtime_error("trial inventory or wood class unavailable");

    if (action == "stock" || action == "stock-unsaved") {
        OnlyWoodStack(inventory, wood, 0);
        auto* item = AddWood(world, inventory, wood, 7, false);
        if (!item)
            throw std::runtime_error("engine refused to add trial wood");
        auto* stack = OnlyWoodStack(inventory, wood, 7);
        if (action == "stock-unsaved") {
            log->info("Inventory trial stock interrupted before world save id={} wood=7", expectedId);
            return;
        }
        stack->IncrementItemQuantity(-3, true, false, false, false, false, false);
        OnlyWoodStack(inventory, wood, 4);
        gameMode->SaveWorld(true, false, false);
        log->info("Inventory trial stocked id={} wood_before=0 wood_added=7 wood_after=4", expectedId);
    } else if (action == "clear") {
        auto* stack = OnlyWoodStack(inventory, wood, 4);
        const auto itemId = stack->ItemIDField();
        if (!inventory->RemoveItem(&itemId, false, false, false, false))
            throw std::runtime_error("engine refused to remove trial stack");
        OnlyWoodStack(inventory, wood, 0);
        gameMode->SaveWorld(true, false, false);
        log->info("Inventory trial cleared id={} wood_before=4 wood_after=0 owner_player={}",
                  expectedId, box->OwningPlayerIDField());
    } else if (action == "capacity") {
        ProbeCapacity(world, inventory, wood, expectedId);
    } else if (action == "verify-empty") {
        OnlyWoodStack(inventory, wood, 0);
        log->info("Inventory trial verified empty id={} owner_player={}", expectedId, box->OwningPlayerIDField());
    } else {
        throw std::runtime_error("unknown inventory probe action");
    }
}

int ObserveTrialWood(UWorld* world, AShooterGameMode* gameMode, unsigned expectedId) {
    RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2Inventory");
    auto* boxClass = TSoftClassPtr<APrimalStructureItemContainer>(BoxClass).LoadSynchronous();
    auto* inventory = FindTrialBox(world, boxClass, expectedId)->MyInventoryComponentField();
    if (!inventory)
        throw std::runtime_error("inventory is unobserved");
    auto& items = inventory->InventoryItemsField();
    if (items.Num() == 0)
        return 0;
    auto* wood = TSoftClassPtr<UPrimalItem>(WoodItem).LoadSynchronous();
    if (!wood || items.Num() != 1 || !items[0] || items[0]->ClassField() != wood)
        throw std::runtime_error("inventory composition is outside the trial");
    return items[0]->GetItemQuantity();
}
}
