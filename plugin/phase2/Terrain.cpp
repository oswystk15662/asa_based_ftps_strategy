#include "API/ARK/Ark.h"
#include "Terrain.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <numbers>
#include <stdexcept>

namespace Phase2 {
namespace {
using Json = nlohmann::json;

Json TraceColumn(UWorld* world, const Trace& column, UScriptStruct* hitType) {
    // The AsaApi FHitResult wrapper exposes offsets and has no native storage of its own.
    alignas(64) std::array<std::byte, 1024> storage{};
    auto* hit = reinterpret_cast<FHitResult*>(storage.data());
    hitType->InitializeStruct(hit, 1);
    struct Cleanup {
        UScriptStruct* type;
        FHitResult* hit;
        ~Cleanup() { type->DestroyStruct(hit, 1); }
    } cleanup{hitType, hit};

    const FVector start(column[0], column[1], column[2]);
    const FVector end(column[0], column[1], column[3]);
    Json result = {{"trace_cm", column}, {"status", "unobserved"}};
    if (!UVictoryCore::VTraceSingleBP(world, hit, &start, &end, ECollisionChannel::ECC_Visibility,
                                      0, FName{}, false, nullptr, 0.f))
        return result;

    const auto& point = hit->ImpactPointField();
    // The SDK forward-declares FVector_NetQuantizeNormal. Read its UE double-vector base.
    const auto& normal = *GetNativePointerField<const FVector*>(hit, "FHitResult.ImpactNormal");
    result["point_cm"] = {point.X, point.Y, point.Z};
    result["normal"] = {normal.X, normal.Y, normal.Z};
    result["status"] = "unclassified_hit";
    if (auto* component = hit->ComponentField().Get()) {
        result["component"] = component->ClassField()->NameField().ToString().ToStringUTF8();
        if (auto* owner = component->OwnerPrivateField()) {
            auto* ownerClass = owner->ClassField();
            result["actor_class"] = ownerClass->NameField().ToString().ToStringUTF8();
            if (auto* landscapeClass = ALandscapeProxy::StaticClass()) {
                if (ownerClass->IsChildOf(landscapeClass) && !hit->bStartPenetrating().Get() &&
                    std::abs(normal.SizeSquared() - 1.0) <= 0.02 && normal.Z > 0.0) {
                    result["status"] = "landscape";
                    result["slope_deg"] = std::acos(std::clamp(normal.Z, 0.0, 1.0))
                        * 180.0 / std::numbers::pi;
                } else {
                    result["status"] = "blocked";
                }
            }
        }
    }
    return result;
}

UScriptStruct* GetHitType() {
    auto* hitType = FindScriptStruct(L"/Script/Engine.HitResult");
    if (!hitType || hitType->PropertiesSizeField() <= 0 || hitType->PropertiesSizeField() > 1024 ||
        hitType->MinAlignmentField() <= 0 || 64 % hitType->MinAlignmentField() != 0)
        throw std::runtime_error("unexpected native HitResult layout");
    return hitType;
}

std::vector<APhysicsVolume*> WaterVolumes(UWorld* world) {
    auto* type = APhysicsVolume::StaticClass();
    if (!type)
        throw std::runtime_error("physics volume class unavailable");
    TArray<AActor*> actors;
    UGameplayStatics::GetAllActorsOfClass(world, type, &actors);
    std::vector<APhysicsVolume*> volumes;
    for (auto* actor : actors) {
        auto* volume = static_cast<APhysicsVolume*>(actor);
        if (volume && volume->bWaterVolume().Get())
            volumes.push_back(volume);
    }
    return volumes;
}

bool InsideWater(const std::vector<APhysicsVolume*>& volumes, FVector point) {
    return std::any_of(volumes.begin(), volumes.end(), [&point](APhysicsVolume* volume) {
        float distance = 0.f;
        float maxDistance = 0.f;
        return volume->EncompassesPoint(&point, 0.f, &distance, &maxDistance) == 1;
    });
}
}  // namespace

Json ObserveTerrain(UWorld* world, const std::vector<Trace>& traces, bool surveyWater) {
    Json results = Json::array();
    auto* hitType = GetHitType();
    const auto volumes = surveyWater ? WaterVolumes(world) : std::vector<APhysicsVolume*>{};
    for (const auto& trace : traces) {
        auto result = TraceColumn(world, trace, hitType);
        if (surveyWater && result.at("status") == "landscape") {
            const auto z = result.at("point_cm")[2].get<double>();
            const FVector point(trace[0], trace[1], z + 75.0);
            result["water_volume_probe"] = {
                {"checked", volumes.size()}, {"inside", InsideWater(volumes, point)}, {"z_cm", point.Z}
            };
        }
        results.push_back(std::move(result));
    }
    return results;
}
double FoundationGroundZ(UWorld* world, double x, double y, double halfX, double halfY) {
    auto* hitType = GetHitType();
    const auto volumes = WaterVolumes(world);
    if (volumes.empty())
        throw std::runtime_error("no water volumes available for placement preflight");
    const std::array columns{
        Trace{x, y, 80000, -80000},
        Trace{x - halfX, y - halfY, 80000, -80000},
        Trace{x - halfX, y + halfY, 80000, -80000},
        Trace{x + halfX, y - halfY, 80000, -80000},
        Trace{x + halfX, y + halfY, 80000, -80000}
    };
    double minZ = std::numeric_limits<double>::infinity();
    double maxZ = -minZ;
    double centerZ = 0;
    for (std::size_t i = 0; i < columns.size(); ++i) {
        const auto& column = columns[i];
        const auto result = TraceColumn(world, column, hitType);
        if (result.at("status") != "landscape")
            throw std::runtime_error("footprint is obstructed or unobserved");
        if (result.at("slope_deg").get<double>() > 5.0)
            throw std::runtime_error("footprint slope exceeds five degrees");
        const auto z = result.at("point_cm")[2].get<double>();
        if (InsideWater(volumes, FVector(column[0], column[1], z + 75.0)))
            throw std::runtime_error("footprint intersects a water volume");
        if (i == 0)
            centerZ = z;
        minZ = std::min(minZ, z);
        maxZ = std::max(maxZ, z);
    }
    if (maxZ - minZ > 25.0)
        throw std::runtime_error("footprint elevation varies by more than 25 cm");
    return centerZ;
}

}  // namespace Phase2
