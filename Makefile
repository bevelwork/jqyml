.PHONY: run test test-jqx test-state test-anchors test-server test-speed test-doom-jq test-doom-jq-frame test-doom-jq-loop test-doom-jq-game test-doom-jq-runner speed up send docker-up docker-down docker-send

JQYML_DIR := $(CURDIR)
PORT := 8888

# Speed test: run a single test N times and report duration (e.g. make speed ITERATIONS=100)
ITERATIONS ?= 50
SPEED_YAML ?= tests/03_simple_key_value.yaml

run:
	jq -R -s -rf run.jq < test.yml

# Run state.jq tests: each tests/state/*.json (except parse_*) has matching .expected
STATE_JQ_TESTS := $(filter-out parse_state,$(patsubst tests/state/%.json,%,$(wildcard tests/state/*.json)))
test-state:
	@failed=0; \
	for name in $(STATE_JQ_TESTS); do \
	  echo "Testing state $$name..."; \
	  out=$$(mktemp); \
	  (cat "tests/state/$$name.json" | jq -c -L . -f state.jq > "$$out" 2>/dev/null); ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED (jq exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; continue; fi; \
	  if ! diff -q "tests/state/$$name.expected" "$$out" >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; diff "tests/state/$$name.expected" "$$out" || true; failed=$$((failed+1)); fi; \
	  rm -f "$$out"; \
	done; \
	echo "Testing state parse_state (YAML -> run.jq)..."; \
	out=$$(mktemp); \
	(jq -R -s -L . -rf run.jq < tests/state/parse_state.yaml 2>/dev/null | jq -c . > "$$out"); ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED (parse exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; else \
	  if ! diff -q tests/state/parse_state.expected "$$out" >/dev/null 2>&1; then echo "  FAILED (parse output mismatch)"; diff tests/state/parse_state.expected "$$out" || true; failed=$$((failed+1)); fi; \
	fi; rm -f "$$out"; \
	[ $$failed -eq 0 ] && echo "All state tests passed." || { echo "$$failed state test(s) failed."; exit 1; }

# Run anchor/alias unit tests: each tests/anchors/*.yaml has matching .expected (compact JSON)
ANCHOR_TESTS := $(patsubst tests/anchors/%.yaml,%,$(wildcard tests/anchors/*.yaml))
test-anchors:
	@failed=0; \
	for name in $(ANCHOR_TESTS); do \
	  echo "Testing anchors $$name..."; \
	  out=$$(mktemp); \
	  (jq -R -s -L . -rf run.jq < "tests/anchors/$$name.yaml" 2>/dev/null | jq -c . > "$$out"); ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED (parse exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; continue; fi; \
	  if ! diff -q "tests/anchors/$$name.expected" "$$out" >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; diff "tests/anchors/$$name.expected" "$$out" || true; failed=$$((failed+1)); fi; \
	  rm -f "$$out"; \
	done; \
	[ $$failed -eq 0 ] && echo "All anchor tests passed." || { echo "$$failed anchor test(s) failed."; exit 1; }

# Doom-in-jq (Phase 1): frame schema, game loop, runner.
DOOM_JQ_DIR := $(JQYML_DIR)/doom_jq
DOOM_JQ_JQ := $(DOOM_JQ_DIR)/jq
test-doom-jq-frame:
	@echo "Testing doom_jq frame.jq (static frame)..."; \
	out=$$(cd $(JQYML_DIR) && jq -n -L doom_jq/jq -f doom_jq/jq/frame.jq -c 2>/dev/null); ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED (jq exit $$ret)"; exit 1; fi; \
	if ! echo "$$out" | diff -q - doom_jq/tests/frame_static.expected >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; echo "$$out" | diff - doom_jq/tests/frame_static.expected || true; exit 1; fi; \
	echo "  OK"
test-doom-jq-loop:
	@echo "Testing doom_jq loop.jq (one tic)..."; \
	out=$$(cd $(JQYML_DIR) && echo '{"state":null,"input":{"keys":[]}}' | jq -L doom_jq/jq -f doom_jq/jq/loop.jq -c 2>/dev/null); ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED (jq exit $$ret)"; exit 1; fi; \
	if ! echo "$$out" | diff -q - doom_jq/tests/loop_one_tic.expected >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; echo "$$out" | diff - doom_jq/tests/loop_one_tic.expected || true; exit 1; fi; \
	echo "  OK"
test-doom-jq-game:
	@echo "Testing doom_jq game.jq (Phase 2 menu)..."; \
	out=$$(cd $(JQYML_DIR) && echo '{"state":null,"input":{"keys":[]}}' | jq -L doom_jq/jq -f doom_jq/jq/game.jq -c 2>/dev/null); ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED game.jq initial (jq exit $$ret)"; exit 1; fi; \
	if ! echo "$$out" | diff -q - doom_jq/tests/game_menu_initial.expected >/dev/null 2>&1; then echo "  FAILED (initial menu mismatch)"; echo "$$out" | diff - doom_jq/tests/game_menu_initial.expected || true; exit 1; fi; \
	out=$$(cd $(JQYML_DIR) && echo '{"state":{"mode":"menu","menu":{"screen":"main","items":["New Game","Options","Read This","Quit DOOM"],"selected":0}},"input":{"keys":["Enter"]}}' | jq -L doom_jq/jq -f doom_jq/jq/game.jq -c 2>/dev/null); \
	if ! echo "$$out" | diff -q - doom_jq/tests/game_newgame_episode.expected >/dev/null 2>&1; then echo "  FAILED (New Game -> episode)"; echo "$$out" | diff - doom_jq/tests/game_newgame_episode.expected || true; exit 1; fi; \
	out=$$(cd $(JQYML_DIR) && echo '{"state":{"mode":"menu","menu":{"screen":"episode","items":["E1","E2","E3"],"selected":0}},"input":{"keys":["Enter"]}}' | jq -L doom_jq/jq -f doom_jq/jq/game.jq -c 2>/dev/null); \
	if ! echo "$$out" | diff -q - doom_jq/tests/game_episode_skill.expected >/dev/null 2>&1; then echo "  FAILED (episode -> skill)"; echo "$$out" | diff - doom_jq/tests/game_episode_skill.expected || true; exit 1; fi; \
	echo "  OK"
test-doom-jq-game-level:
	@echo "Testing doom_jq game.jq (Phase 3.1 level load, player spawn)..."; \
	f='{state: {mode: "menu", menu: {screen: "skill", items: ["Baby","Easy","Normal","Hard","Nightmare"], selected: 2, episode: 1}}, input: {keys: ["Enter"], level: $$level[0]}}'; \
	payload=$$(cd $(JQYML_DIR) && jq -n -c --slurpfile level doom_jq/data/e1m1.json "$$f"); \
	out=$$(cd $(JQYML_DIR) && echo "$$payload" | jq -L doom_jq/jq -f doom_jq/jq/game.jq -c 2>/dev/null); ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED game.jq level (jq exit $$ret)"; exit 1; fi; \
	if ! echo "$$out" | jq -e '.state.mode == "game" and (.state.level | type == "object") and (.state.level.vertexes | length == 4) and .state.player.x == 128 and .state.player.y == 128 and .state.player.angle == 90 and .state.player.health == 100' >/dev/null 2>&1; then echo "  FAILED (level/player spawn assertion)"; echo "$$out" | jq .; exit 1; fi; \
	if ! echo "$$out" | jq -e '.frame.map != null and (.frame.map.lines | length == 4) and .frame.map.player.x == 128 and .frame.map.player.y == 128 and .frame.map.player.angle == 90' >/dev/null 2>&1; then echo "  FAILED (Phase 4.0 map frame assertion)"; echo "$$out" | jq .; exit 1; fi; \
	echo "  OK"
test-doom-jq-runner:
	@echo "Testing doom_jq runner.py (--headless, --loop --headless)..."; \
	cd $(JQYML_DIR) && python3 doom_jq/runner.py --headless 2>/dev/null; ret1=$$?; \
	cd $(JQYML_DIR) && python3 doom_jq/runner.py --loop --headless 2>/dev/null; ret2=$$?; \
	if [ $$ret1 -ne 0 ]; then echo "  FAILED runner --headless (exit $$ret1)"; exit 1; fi; \
	if [ $$ret2 -ne 0 ]; then echo "  FAILED runner --loop --headless (exit $$ret2)"; exit 1; fi; \
	echo "  OK"
# Phase 3.0: E1M1 JSON schema and WAD export
test-doom-jq-wad:
	@echo "Testing doom_jq E1M1 data (schema validation)..."; \
	python3 $(DOOM_JQ_DIR)/tools/wad2json.py --validate $(DOOM_JQ_DIR)/data/e1m1.json 2>/dev/null; ret=$$?; \
	if [ $$ret -ne 0 ]; then echo "  FAILED (e1m1.json schema)"; exit 1; fi; \
	echo "  OK"

test-doom-jq: test-doom-jq-frame test-doom-jq-loop test-doom-jq-game test-doom-jq-game-level test-doom-jq-runner test-doom-jq-wad
	@echo "All doom_jq tests passed."

# Run YAML parser and jqx tests.
# If tests/<name>.expected exists, compare run.jq output to it; else only check exit code.
TEST_YAMLS := $(wildcard tests/*.yaml)
test: test-jqx test-state test-anchors test-speed test-server test-doom-jq
	@failed=0; \
	for f in $(TEST_YAMLS); do \
	  echo "Testing $$f..."; \
	  base="$${f%.yaml}"; \
	  out=$$(mktemp); \
	  (jq -R -s -L . -rf run.jq < "$$f" 2>/dev/null | jq -c . > "$$out"); ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED (parse exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; continue; fi; \
	  if [ -f "$$base.expected" ]; then \
	    if ! diff -q "$$base.expected" "$$out" >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; diff "$$base.expected" "$$out" || true; failed=$$((failed+1)); fi; \
	  fi; \
	  rm -f "$$out"; \
	done; \
	[ $$failed -eq 0 ] && echo "All tests passed." || { echo "$$failed test(s) failed."; exit 1; }

# Run jqx tests: each tests/jqx/*.jqx (except *.header.jqx, *.head.jqx, *.footer.jqx) has matching .json and .expected.
# Optional composition: .header.jqx -> <Header />, .head.jqx -> <Head />, .footer.jqx -> <Footer /> (all paths under tests/jqx/).
EMPTY_JQX := $(JQYML_DIR)/empty.jqx
JQX_TESTS := $(filter-out %.header %.head %.footer,$(patsubst tests/jqx/%.jqx,%,$(wildcard tests/jqx/*.jqx)))
test-jqx:
	@failed=0; \
	for name in $(JQX_TESTS); do \
	  echo "Testing jqx $$name..."; \
	  out=$$(mktemp); \
	  hdr="$(EMPTY_JQX)"; [ -f "tests/jqx/$$name.header.jqx" ] && hdr="$(JQYML_DIR)/tests/jqx/$$name.header.jqx"; \
	  headf="$(EMPTY_JQX)"; [ -f "tests/jqx/$$name.head.jqx" ] && headf="$(JQYML_DIR)/tests/jqx/$$name.head.jqx"; \
	  footf="$(EMPTY_JQX)"; [ -f "tests/jqx/$$name.footer.jqx" ] && footf="$(JQYML_DIR)/tests/jqx/$$name.footer.jqx"; \
	  (cat "tests/jqx/$$name.json" | jq -r --rawfile tmpl "tests/jqx/$$name.jqx" --rawfile header "$$hdr" --rawfile head "$$headf" --rawfile footer "$$footf" -L . -f jqx.jq > "$$out" 2>&1); ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED (jq exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; continue; fi; \
	  if ! diff -q "tests/jqx/$$name.expected" "$$out" >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; diff "tests/jqx/$$name.expected" "$$out" || true; failed=$$((failed+1)); fi; \
	  rm -f "$$out"; \
	done; \
	[ $$failed -eq 0 ] && echo "All jqx tests passed." || { echo "$$failed jqx test(s) failed."; exit 1; }

up:
	docker compose build jqyml && docker compose up -d

down:
	docker compose down

# Sanity-check 413, 404, and GET /state. Starts server on TEST_PORT, then kills it.
# Requires: PyYAML (pip install pyyaml), jq in PATH.
TEST_PORT ?= 18888
test-server:
	@dd if=/dev/zero of=/tmp/jqyml_big bs=1000001 count=1 2>/dev/null; \
	cd $(JQYML_DIR) && PORT=$(TEST_PORT) /usr/bin/python3 server.py >/tmp/jqyml_server.log 2>&1 & pid=$$!; \
	sleep 1; \
	up=$$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://127.0.0.1:$(TEST_PORT)/ 2>/dev/null); \
	if [ "$$up" = "000" ] || [ -z "$$up" ]; then \
	  kill $$pid 2>/dev/null || true; \
	  echo "Server did not start (code=$$up). Run: pip install pyyaml"; exit 1; \
	fi; \
	failed=0; \
	code=$$(curl -s -o /tmp/jqyml_413 -w "%{http_code}" -X POST -H "Content-Length: 1000001" --data-binary @/tmp/jqyml_big http://127.0.0.1:$(TEST_PORT)/ 2>/dev/null); \
	if [ "$$code" != "413" ]; then echo "  FAILED: POST with oversized body returned $$code (expected 413)"; failed=$$((failed+1)); fi; \
	grep -q "Request entity too large" /tmp/jqyml_413 2>/dev/null || { echo "  FAILED: 413 body should contain 'Request entity too large'"; failed=$$((failed+1)); }; \
	code=$$(curl -s -o /tmp/jqyml_404 -w "%{http_code}" http://127.0.0.1:$(TEST_PORT)/nonexistent 2>/dev/null); \
	if [ "$$code" != "404" ]; then echo "  FAILED: GET /nonexistent returned $$code (expected 404)"; failed=$$((failed+1)); fi; \
	grep -q "404" /tmp/jqyml_404 2>/dev/null || { echo "  FAILED: 404 page should contain '404'"; failed=$$((failed+1)); }; \
	code=$$(curl -s -o /tmp/jqyml_state -w "%{http_code}" http://127.0.0.1:$(TEST_PORT)/state 2>/dev/null); \
	if [ "$$code" != "200" ]; then echo "  FAILED: GET /state returned $$code (expected 200)"; failed=$$((failed+1)); fi; \
	grep -q '"counter"' /tmp/jqyml_state 2>/dev/null || { echo "  FAILED: GET /state body should contain \"counter\""; failed=$$((failed+1)); }; \
	code=$$(curl -s -o /tmp/jqyml_index -w "%{http_code}" http://127.0.0.1:$(TEST_PORT)/ 2>/dev/null); \
	if [ "$$code" != "200" ]; then echo "  FAILED: GET / returned $$code (expected 200)"; failed=$$((failed+1)); fi; \
	grep -q '<!DOCTYPE html>' /tmp/jqyml_index 2>/dev/null || { echo "  FAILED: GET / body should contain '<!DOCTYPE html>' (got error output?)"; cat /tmp/jqyml_index >&2; failed=$$((failed+1)); }; \
	grep -q 'Visitor count' /tmp/jqyml_index 2>/dev/null || { echo "  FAILED: GET / body should contain 'Visitor count' (state in header)"; failed=$$((failed+1)); }; \
	grep -q 'Conversions:' /tmp/jqyml_index 2>/dev/null || { echo "  FAILED: GET / body should contain 'Conversions:' (conversion count state)"; failed=$$((failed+1)); }; \
	kill $$pid 2>/dev/null || true; \
	rm -f /tmp/jqyml_big /tmp/jqyml_413 /tmp/jqyml_404 /tmp/jqyml_state /tmp/jqyml_index /tmp/jqyml_server.log; \
	if [ $$failed -eq 0 ]; then echo "test-server: 413, 404, GET /state, GET / OK (index shows Visitor count + Conversions)"; else echo "$$failed check(s) failed"; exit 1; fi

# Speed test: run run.jq on SPEED_YAML ITERATIONS times; report total and per-iteration time.
# Override: make speed ITERATIONS=1000 SPEED_YAML=tests/14_anchors_used.yaml
test-speed:
	@echo "Running speed test ($(ITERATIONS) iterations)..."; \
	cd $(JQYML_DIR) && ITERATIONS="$(ITERATIONS)" SPEED_YAML="$(SPEED_YAML)" /usr/bin/python3 scripts/speed.py

speed: test-speed

# POST test.yml to containerized service (run "make up" first).
send:
	@curl -s -S --connect-timeout 5 --max-time 15 -X POST --data-binary @test.yml http://localhost:8080/
