#include "API/ARK/Ark.h"
#include "IApiUtils.h"
#include "ICommands.h"
#include "Logger/Logger.h"
#include "Requests.h"
#include "phase2/ClientTrial.h"
#include "phase2/Foundation.h"
#include "phase2/Inventory.h"
#include "phase2/NpcSurvey.h"
#include "phase2/NpcTrial.h"
#include "phase2/Terrain.h"

#include <algorithm>
#include <chrono>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <cstddef>
#include <objbase.h>
#include <optional>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

constexpr char BaseUrl[] = "http://127.0.0.1:8765";
constexpr char PluginName[] = "AsaCivilizationPhase1";
constexpr std::size_t MaxReply = 16'384;
constexpr std::size_t MaxTraces = 8;
using Phase2::Trace;

struct State {
    std::string bootId;
    std::string build;
    std::string token;
    std::string commandId;
    std::vector<Trace> traces;
    Json pending;
    std::uint64_t ack{};
    Clock::time_point next{};
    Clock::time_point nextClientSample{};
    std::chrono::milliseconds backoff{500};
    bool inFlight{};
    bool connected{};
    bool inspectFoundation{};
    bool surveyWater{};
    bool clientTrial{};
    std::string foundationAction;
    std::string inventoryAction;
    std::optional<Phase2::NpcSurvey> npcSurvey;
    std::optional<Phase2::NpcTrial> npcTrial;
    unsigned trialStructureId{};
    bool mirrorInventory{};
};
State state;

std::string Env(const char* name) {
    const char* value = std::getenv(name);
    return value ? value : "";
}

std::string NewBootId() {
    GUID guid{};
    wchar_t text[39]{};
    if (FAILED(CoCreateGuid(&guid)) || !StringFromGUID2(guid, text, 39))
        throw std::runtime_error("Could not generate a boot UUID");
    std::string result;
    for (int i = 1; i < 37; ++i) {
        const char ch = static_cast<char>(text[i]);
        result += ch >= 'A' && ch <= 'F' ? ch - 'A' + 'a' : ch;
    }
    return result;
}

void Disconnected() {
    if (state.backoff == 500ms)
        Log::GetLog()->warn("Phase 1 bridge request failed. Retrying with hello");
    state.connected = false;
    state.next = Clock::now() + state.backoff;
    state.backoff = std::min(state.backoff * 2, 8'000ms);
}

Json Envelope() {
    return {{"protocol", 1}, {"world_id", "phase1"}, {"boot_id", state.bootId}};
}

// This callback is delivered by AsaApi on its tick path. The response is a small envelope.
void Receive(bool hello, bool ok, const std::string& body) {
    state.inFlight = false;
    if (!ok || body.size() > MaxReply) {
        Disconnected();
        return;
    }
    try {
        const auto reply = Json::parse(body);
        if (reply.at("protocol") != 1 || reply.at("world_id") != "phase1" ||
            reply.at("boot_id") != state.bootId || !reply.at("ack").is_number_unsigned())
            throw std::runtime_error("invalid bridge response");
        const auto& command = reply.at("command");
        const auto commandId = command.at("command_id").get<std::string>();
        if (command.at("kind") != "observe_server" || commandId.size() != 36)
            throw std::runtime_error("invalid command");

        std::vector<Trace> traces;
        if (auto field = command.find("terrain_traces_cm"); field != command.end()) {
            if (!field->is_array() || field->size() > MaxTraces)
                throw std::runtime_error("invalid trace batch");
            for (const auto& entry : *field) {
                if (!entry.is_array() || entry.size() != 4)
                    throw std::runtime_error("invalid trace coordinates");
                Trace trace{};
                for (std::size_t i = 0; i < trace.size(); ++i) {
                    if (!entry[i].is_number())
                        throw std::runtime_error("invalid trace coordinate type");
                    trace[i] = entry[i].get<double>();
                    if (!std::isfinite(trace[i]) || std::abs(trace[i]) > 2'000'000)
                        throw std::runtime_error("out-of-range trace coordinate");
                }
                if (trace[2] <= trace[3] || trace[2] - trace[3] > 200'000)
                    throw std::runtime_error("invalid trace depth");
                traces.push_back(trace);
            }
        }
        if (commandId == state.commandId && traces != state.traces)
            throw std::runtime_error("command contents changed without a new ID");

        const auto ack = reply.at("ack").get<std::uint64_t>();
        if (!hello && (state.pending.is_null() || commandId != state.commandId ||
                       ack != state.pending.at("seq").get<std::uint64_t>()))
            throw std::runtime_error("unexpected acknowledgment");

        // A bridge restart yields a new command ID. Re-observe using its fresh cursor.
        if (commandId != state.commandId || !hello ||
            (!state.pending.is_null() && ack + 1 != state.pending.at("seq").get<std::uint64_t>()))
            state.pending = nullptr;
        if (!state.connected)
            Log::GetLog()->info("Phase 1 bridge connected. ASA build={} cursor={}", state.build, ack);
        state.ack = ack;
        state.commandId = commandId;
        state.traces = std::move(traces);
        state.connected = true;
        state.backoff = 500ms;
        state.next = Clock::now() + 250ms;
    } catch (const std::exception&) {
        Disconnected();
    }
}

void Tick(float) {
    auto& api = AsaApi::GetApiUtils();
    if (api.GetStatus() != AsaApi::ServerStatus::Ready || state.inFlight || Clock::now() < state.next)
        return;
    const auto world = api.GetWorld();
    const auto gameMode = api.GetShooterGameMode();
    if (!world || !gameMode)
        return;

    if (state.clientTrial && Clock::now() >= state.nextClientSample) {
        state.nextClientSample = Clock::now() + 5s;
        try {
            Phase2::LogClientTrial(world, gameMode);
        } catch (const std::exception& error) {
            state.clientTrial = false;
            Log::GetLog()->error("Client trial stopped: {}", error.what());
        }
    }
    if (state.npcSurvey)
        state.npcSurvey->Tick(world, gameMode);
    if (state.npcTrial)
        state.npcTrial->Tick(world, gameMode);
    if (!state.foundationAction.empty()) {
        const auto action = std::exchange(state.foundationAction, {});
        try {
            Phase2::RunFoundationProbe(world, gameMode, action, state.trialStructureId);
        } catch (const std::exception& error) {
            Log::GetLog()->error("Foundation probe rejected: {}", error.what());
        }
    }
    if (!state.inventoryAction.empty()) {
        const auto action = std::exchange(state.inventoryAction, {});
        try {
            Phase2::RunInventoryProbe(world, gameMode, action, state.trialStructureId);
        } catch (const std::exception& error) {
            Log::GetLog()->error("Inventory trial rejected: {}", error.what());
        }
    }
    if (state.inspectFoundation) {
        state.inspectFoundation = false;
        try {
            Phase2::LoadFoundationClass();
        } catch (const std::exception& error) {
            Log::GetLog()->error("Wood foundation inspection failed: {}", error.what());
        }
    }

    const bool hello = !state.connected;
    Json request = Envelope();
    if (hello) {
        request["api_version"] = "2.11";
        request["server_build"] = state.build;
    } else {
        if (state.pending.is_null()) {
            FString map;
            gameMode->GetMapName(&map);
            int players = 0;
            for (auto& controller : world->PlayerControllerListField()) {
                if (controller.Get())
                    ++players;
            }
            state.pending = std::move(request);
            state.pending["seq"] = state.ack + 1;
            state.pending["command_id"] = state.commandId;
            state.pending["snapshot"] = {
                {"map", map.ToString()}, {"game_seconds", static_cast<double>(world->TimeSecondsField())},
                {"players", players}
            };
            if (state.mirrorInventory) {
                try {
                    const int wood = Phase2::ObserveTrialWood(world, gameMode, state.trialStructureId);
                    state.pending["snapshot"]["inventory"] = {
                        {"structure_id", state.trialStructureId}, {"wood", wood}
                    };
                } catch (const std::exception& error) {
                    Log::GetLog()->warn("Inventory observation unavailable: {}", error.what());
                    state.pending = nullptr;
                    state.next = Clock::now() + 2s;
                    return;
                }
            }
            if (state.ack == 0 && !state.traces.empty()) {
                try {
                    state.pending["snapshot"]["terrain"] = Phase2::ObserveTerrain(world, state.traces, state.surveyWater);
                } catch (const std::exception& error) {
                    Log::GetLog()->error("Terrain observation failed: {}", error.what());
                }
            }
        }
        request = state.pending;
    }

    state.inFlight = API::Requests::Get().CreatePostRequest(
        std::string(BaseUrl) + (hello ? "/v1/hello" : "/v1/exchange"),
        [hello](bool ok, std::string body, std::unordered_map<std::string, std::string>) {
            Receive(hello, ok, body);
        },
        request.dump(), "application/json", {"Authorization: Bearer " + state.token}, 2, 2, 2);
    if (!state.inFlight)
        Disconnected();
}
}  // namespace

void Initialize() {
    Log::Get().Init(PluginName);
    state = {};
    state.token = Env("ASA_PHASE1_TOKEN");
    state.build = Env("ASA_PHASE1_SERVER_BUILD");
    state.inspectFoundation = Env("ASA_PHASE2_INSPECT_FOUNDATION") == "1";
    state.surveyWater = Env("ASA_PHASE2_SURVEY_WATER") == "1";
    state.clientTrial = Env("ASA_PHASE2_CLIENT_TRIAL") == "1";
    state.foundationAction = Env("ASA_PHASE2_FOUNDATION_POC");
    state.inventoryAction = Env("ASA_PHASE2_INVENTORY_POC");
    if (Env("ASA_PHASE2_HUMAN_NPC_SURVEY") == "1")
        state.npcSurvey.emplace();
    if (Env("ASA_PHASE2_HUMAN_NPC_TRIAL") == "1")
        state.npcTrial.emplace();
    if (!state.foundationAction.empty() && !state.inventoryAction.empty())
        throw std::runtime_error("enable only one trial per boot");
    state.mirrorInventory = Env("ASA_PHASE2_INVENTORY_MIRROR") == "1";
    const auto id = Env((state.inventoryAction.empty() && !state.mirrorInventory)
                        ? "ASA_PHASE2_FOUNDATION_ID" : "ASA_PHASE2_INVENTORY_ID");
    if (!id.empty()) {
        const auto [end, error] = std::from_chars(id.data(), id.data() + id.size(), state.trialStructureId);
        if (error != std::errc{} || end != id.data() + id.size())
            throw std::runtime_error("invalid Phase 2 trial structure ID");
    }
    if (state.mirrorInventory && (!state.trialStructureId || !state.foundationAction.empty()))
        throw std::runtime_error("inventory mirror requires a trial inventory ID");
    if (state.token.size() < 16 || state.token.size() > 128 ||
        !std::all_of(state.token.begin(), state.token.end(), [](char ch) {
            return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9');
        }) || state.build.empty() || state.build.size() > 80)
        throw std::runtime_error("Set ASA_PHASE1_TOKEN and ASA_PHASE1_SERVER_BUILD before starting ASA");

    state.bootId = NewBootId();
    AsaApi::GetCommands().AddOnTickCallback(FString(L"AsaCivilizationPhase1"), Tick);
    Log::GetLog()->info("Phase 1 plugin initialized. ASA build={}", state.build);
}

extern "C" __declspec(dllexport) void Plugin_Init() {
    try {
        Initialize();
    } catch (const std::exception& error) {
        if (auto& logger = Log::GetLog())
            logger->error("Phase 1 initialization failed: {}", error.what());
    }
}

extern "C" __declspec(dllexport) void Plugin_Unload() {
    AsaApi::GetCommands().RemoveOnTickCallback(FString(L"AsaCivilizationPhase1"));
    if (auto& logger = Log::GetLog())
        logger->info("Phase 1 plugin unloaded");
    // AsaApi 2.11 cancels this module's Requests callbacks before freeing the DLL.
}
