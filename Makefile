.PHONY: run test test-jqx test-state test-anchors up send docker-up docker-down docker-send

JQYML_DIR := $(CURDIR)
PORT := 8888

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

# Run YAML parser and jqx tests.
TEST_YAMLS := $(wildcard tests/*.yaml)
test: test-jqx test-state test-anchors
	@failed=0; \
	for f in $(TEST_YAMLS); do \
	  echo "Testing $$f..."; \
	  jq -R -s -rf run.jq < "$$f" >/dev/null 2>&1; ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED"; failed=$$((failed+1)); fi; \
	done; \
	[ $$failed -eq 0 ] && echo "All tests passed." || { echo "$$failed test(s) failed."; exit 1; }

# Run jqx tests: each tests/jqx/*.jqx has matching .json and .expected
JQX_TESTS := $(patsubst tests/jqx/%.jqx,%,$(wildcard tests/jqx/*.jqx))
test-jqx:
	@failed=0; \
	for name in $(JQX_TESTS); do \
	  echo "Testing jqx $$name..."; \
	  out=$$(mktemp); \
	  (cat "tests/jqx/$$name.json" | jq -r --rawfile tmpl "tests/jqx/$$name.jqx" -L . -f jqx.jq > "$$out" 2>&1); ret=$$?; \
	  if [ $$ret -ne 0 ]; then echo "  FAILED (jq exit $$ret)"; failed=$$((failed+1)); rm -f "$$out"; continue; fi; \
	  if ! diff -q "tests/jqx/$$name.expected" "$$out" >/dev/null 2>&1; then echo "  FAILED (output mismatch)"; diff "tests/jqx/$$name.expected" "$$out" || true; failed=$$((failed+1)); fi; \
	  rm -f "$$out"; \
	done; \
	[ $$failed -eq 0 ] && echo "All jqx tests passed." || { echo "$$failed jqx test(s) failed."; exit 1; }

up:
	docker compose build jqyml && docker compose up -d

down:
	docker compose down

# POST test.yml to containerized service (run "make up" first).
send:
	@curl -s -S --connect-timeout 5 --max-time 15 -X POST --data-binary @test.yml http://localhost:8080/
