#include "API/ARK/Ark.h"
#include "Logger/Logger.h"
#include "NpcSurvey.h"
#include "TrialSite.h"

#include <array>
#include <stdexcept>
#include <unordered_map>

namespace Phase2 {
namespace {
constexpr std::string_view ModRoot = "/Human_NPCs_ASA/";

void ObserveCharacters(UWorld* world, unsigned sample) {
    auto* characterClass = APrimalCharacter::StaticClass();
    if (!characterClass)
        throw std::runtime_error("PrimalCharacter class unavailable");
    TArray<AActor*> characters;
    UGameplayStatics::GetAllActorsOfClass(world, characterClass, &characters);
    std::unordered_map<UClass*, std::string> modClasses;
    unsigned count = 0;
    const auto log = Log::GetLog();
    for (auto* actor : characters) {
        if (!actor || !actor->ClassField())
            continue;
        auto* actorClass = actor->ClassField();
        auto [entry, inserted] = modClasses.try_emplace(actorClass);
        if (inserted) {
            FString path;
            actorClass->GetPathName(nullptr, path);
            auto name = path.ToStringUTF8();
            if (name.starts_with(ModRoot))
                entry->second = std::move(name);
        }
        if (entry->second.empty())
            continue;
        ++count;
        FVector position{};
        if (count <= 5 && actor->GetActorLocation(&position))
            log->info("Human NPC observed sample={} actor={} class={} position=({},{},{})", sample,
                      actor->NameField().ToString().ToStringUTF8(), entry->second, position.X, position.Y, position.Z);
    }
    log->info("Human NPC survey sample={} characters={} mod_characters={}", sample, characters.Num(), count);
}

void VerifyPackagedClasses() {
    // From the Windows server manifest for file 9610763.
    constexpr std::array paths{
        L"/Human_NPCs_ASA/Base_Units/ZKs_Base_Man_BP.ZKs_Base_Man_BP_C",
        L"/Human_NPCs_ASA/Base_Units/ZKs_Base_Female_BP.ZKs_Base_Female_BP_C"
    };
    for (const auto* path : paths) {
        const auto* type = TSoftClassPtr<APrimalCharacter>(path).LoadSynchronous();
        Log::GetLog()->info("Human NPC packaged character resolved={} path={}", type != nullptr,
                           FString(path).ToStringUTF8());
    }
}
}  // namespace

void NpcSurvey::Tick(UWorld* world, AShooterGameMode* gameMode) {
    using namespace std::chrono_literals;
    constexpr std::array intervals{0s, 30s, 90s, 180s, 300s};
    if (sample_ == intervals.size())
        return;
    const auto now = std::chrono::steady_clock::now();
    if (started_ == std::chrono::steady_clock::time_point{})
        started_ = now;
    if (now - started_ < intervals[sample_])
        return;
    try {
        RequireTrial(world, gameMode, L"?AltSaveDirectoryName=Phase2HumanNPCs");
        ObserveCharacters(world, ++sample_);
        if (sample_ == intervals.size())
            VerifyPackagedClasses();
    } catch (const std::exception& error) {
        sample_ = static_cast<unsigned>(intervals.size());
        Log::GetLog()->error("Human NPC survey stopped: {}", error.what());
    }
}
}  // namespace Phase2
