#pragma once

#include <cstdint>

struct APrimalCharacter;
struct APrimalDinoCharacter;
namespace UE::Math { template <typename T> struct TVector; }

namespace Phase2 {
inline constexpr auto HumanNpcClassPath =
    L"/Human_NPCs_ASA/People/ZKs_Punch_Man_BP.ZKs_Punch_Man_BP_C";

std::uint64_t DinoId(APrimalDinoCharacter* npc);
void InitializeController(APrimalCharacter* npc);
void WakeForMovement(APrimalDinoCharacter* npc);
void StopMove(APrimalCharacter* npc);
unsigned RequestMove(APrimalCharacter* npc, const UE::Math::TVector<double>& destination, bool projectDestination);
}
