#!/bin/bash
# WayfindR-LLM Comprehensive Test Script
# Usage: ./scripts/run_tests.sh [SERVER_URL]

SERVER="${1:-http://192.168.0.7:5000}"
PASS=0
FAIL=0

echo "=========================================="
echo "WayfindR-LLM Comprehensive Test Suite"
echo "=========================================="
echo "Server: $SERVER"
echo "Date: $(date)"
echo ""

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected="$5"

    if [ "$method" == "GET" ]; then
        response=$(curl -s "$SERVER$endpoint")
    else
        response=$(curl -s -X "$method" "$SERVER$endpoint" -H "Content-Type: application/json" -d "$data")
    fi

    if echo "$response" | grep -q "$expected"; then
        echo "PASS: $name"
        ((PASS++))
    else
        echo "FAIL: $name"
        echo "  Response: ${response:0:200}"
        ((FAIL++))
    fi
}

echo "1. HEALTH & SYSTEM STATUS"
echo "------------------------------------------"
test_endpoint "Health check" "GET" "/health" "" "mcp_server"

echo ""
echo "2. TELEMETRY ENDPOINTS"
echo "------------------------------------------"
test_endpoint "Add telemetry" "POST" "/telemetry" '{"robot_id":"test_bot","telemetry":{"battery":75,"status":"idle","current_location":"lobby","x":1.0,"y":2.0}}' "success"
test_endpoint "Get robot status" "GET" "/telemetry/status?robot_id=test_bot" "" "success"
test_endpoint "Get telemetry history" "GET" "/telemetry/history/test_bot" "" "success"
test_endpoint "Get telemetry stats" "GET" "/telemetry/stats" "" "total_count"

echo ""
echo "3. ROBOT MANAGEMENT"
echo "------------------------------------------"
test_endpoint "List robots" "GET" "/robots" "" "success"
test_endpoint "Get single robot" "GET" "/robots/test_bot" "" "robot_id"

echo ""
echo "4. MAP ENDPOINTS"
echo "------------------------------------------"
test_endpoint "List floors" "GET" "/map/floors" "" "success"
test_endpoint "Get floor details" "GET" "/map/floors/floor_1" "" "success"
test_endpoint "List waypoints" "GET" "/map/waypoints" "" "success"
test_endpoint "List zones" "GET" "/map/zones" "" "success"
test_endpoint "Map image config" "GET" "/map/image/config" "" "resolution"
test_endpoint "Robot positions on map" "GET" "/map/robots/positions" "" "success"

echo ""
echo "5. CHAT ENDPOINTS"
echo "------------------------------------------"
test_endpoint "Operator chat" "POST" "/chat" '{"message":"Show robot status","user_id":"test"}' "success"
test_endpoint "Robot chat" "POST" "/robot_chat" '{"message":"Where is cafeteria?","robot_id":"test_bot","user_id":"visitor"}' "success"

echo ""
echo "6. SEARCH ENDPOINTS"
echo "------------------------------------------"
test_endpoint "Search telemetry" "GET" "/search/telemetry?q=robots" "" "success"
test_endpoint "Search messages" "GET" "/search/messages?q=cafeteria" "" "success"

echo ""
echo "7. DATA RETRIEVAL"
echo "------------------------------------------"
test_endpoint "Get Qdrant data" "GET" "/data/qdrant" "" "log_id"
test_endpoint "Get PostgreSQL data" "GET" "/data/postgresql" "" "log_id"

echo ""
echo "=========================================="
echo "TEST RESULTS"
echo "=========================================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Total:  $((PASS + FAIL))"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "ALL TESTS PASSED!"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
