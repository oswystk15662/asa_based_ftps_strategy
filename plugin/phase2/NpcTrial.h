#pragma once

#include "json.hpp"

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>

struct UWorld;
struct AShooterGameMode;

namespace Phase2 {
class NpcTrial {
public:
    enum class Movement { None, Observe, StopAtGoal, Unreachable, Unprojected, External };
    explicit NpcTrial(std::optional<std::uint64_t> persistenceId = {}) : persistenceId_(persistenceId) {}
    explicit NpcTrial(Movement movement) : movement_(movement) {}
    void Tick(UWorld* world, AShooterGameMode* gameMode);
    nlohmann::json Observation() const;
    void Offer(const nlohmann::json& command);
private:
    std::chrono::steady_clock::time_point next_{};
    unsigned step_{};
    std::optional<std::uint64_t> persistenceId_;
    Movement movement_{};
    std::uint64_t npcId_{};
    unsigned movementSamples_{};
    bool stopIssued_{};
    double maxDistanceAfterStop_{};
    double goalX_{};
    double goalY_{};
    double goalZ_{};
    std::string externalCommand_;
    const char* externalFailure_{};
    std::chrono::steady_clock::time_point externalDeadline_{};
    std::optional<unsigned> engineResponse_;
    bool everReached_{};
    bool atGoal_{};
};
}
