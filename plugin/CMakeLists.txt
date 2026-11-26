cmake_minimum_required(VERSION 3.24)
project(AsaCivilizationPhase1 LANGUAGES CXX)

if(NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "An x64 MSVC generator is required")
endif()

set(ASAAPI_SOURCE "" CACHE PATH "AsaApi source checkout at the pinned commit")
set(ASAAPI_LIB "" CACHE FILEPATH "AsaApi.lib from the matching release")
set(FMT_INCLUDE "" CACHE PATH "fmt include directory")
set(ASA_PUBLIC "${ASAAPI_SOURCE}/AsaApi/Core/Public")
if(NOT EXISTS "${ASA_PUBLIC}/API/ARK/Ark.h" OR NOT EXISTS "${ASAAPI_LIB}"
   OR NOT EXISTS "${FMT_INCLUDE}/fmt/format.h")
    message(FATAL_ERROR "Set ASAAPI_SOURCE, ASAAPI_LIB and FMT_INCLUDE to the pinned dependencies")
endif()

add_library(AsaCivilizationPhase1 SHARED Main.cpp phase2/Terrain.cpp phase2/Foundation.cpp
    phase2/TrialSite.cpp phase2/Inventory.cpp phase2/NpcSurvey.cpp phase2/NpcTrial.cpp
    phase2/NpcMovement.cpp phase2/NpcPairTrial.cpp phase2/ClientTrial.cpp)
target_compile_features(AsaCivilizationPhase1 PRIVATE cxx_std_20)
target_include_directories(AsaCivilizationPhase1 PRIVATE "${ASA_PUBLIC}" "${ASA_PUBLIC}/API/UE" "${FMT_INCLUDE}")
target_compile_definitions(AsaCivilizationPhase1 PRIVATE UNICODE _UNICODE NOMINMAX FMT_HEADER_ONLY)
target_compile_options(AsaCivilizationPhase1 PRIVATE /bigobj /utf-8 /Zi)
target_link_options(AsaCivilizationPhase1 PRIVATE /DEBUG)
target_link_libraries(AsaCivilizationPhase1 PRIVATE "${ASAAPI_LIB}" ole32)
