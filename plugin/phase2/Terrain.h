#pragma once

#include "json.hpp"

#include <array>
#include <vector>

struct UWorld;

namespace Phase2 {
using Trace = std::array<double, 4>;

nlohmann::json ObserveTerrain(UWorld* world, const std::vector<Trace>& traces, bool surveyWater);
double FoundationGroundZ(UWorld* world, double x, double y, double halfX, double halfY);
}
